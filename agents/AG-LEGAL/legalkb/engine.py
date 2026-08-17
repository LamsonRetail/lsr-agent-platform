"""AnswerEngine — lớp trừu tượng cho engine trả-lời-có-trích-dẫn.

Hiện thực mặc định: NotebookLM qua notebooklm-py (KHÔNG chính thức — có thể gãy
khi Google đổi API). Nếu gãy: viết engine mới (vd Gemini File Search API) cùng
interface, phần còn lại của agent không đổi.

notebooklm-py là thư viện async — NotebookLMEngine chạy một event loop riêng
trong thread nền và expose API sync cho consumer/sync worker (vốn code sync).
"""
import asyncio
import contextlib
import threading
from dataclasses import dataclass, field


@dataclass
class Citation:
    title: str
    url: str
    snippet: str = ""


@dataclass
class EngineAnswer:
    ok: bool
    text: str = ""
    citations: list = field(default_factory=list)
    error: str = ""
    conversation_id: str = ""


class PriorityLock:
    """Lock hai mức: chat (cao) luôn được nhường lượt trước sync (thấp).

    Chat và sync dùng chung một phiên NotebookLM nên phải tuần tự; nếu để sync
    50 tài liệu giành lock liên tục thì người dùng chờ cả chục phút.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cv = threading.Condition()
        self._waiting_high = 0

    @contextlib.contextmanager
    def high(self):
        with self._cv:
            self._waiting_high += 1
        try:
            with self._lock:
                yield
        finally:
            with self._cv:
                self._waiting_high -= 1
                self._cv.notify_all()

    @contextlib.contextmanager
    def low(self):
        with self._cv:
            while self._waiting_high:
                self._cv.wait()
        with self._lock:
            yield


class AnswerEngine:
    """Interface — mọi engine phải có đủ các method này."""

    def ask(self, question, conversation_id=None) -> EngineAnswer:
        raise NotImplementedError

    def add_text_source(self, title, content) -> str:
        """Trả về source_id."""
        raise NotImplementedError

    def add_file_source(self, title, file_path) -> str:
        raise NotImplementedError

    def delete_source(self, source_id):
        raise NotImplementedError

    def list_source_ids(self) -> list:
        raise NotImplementedError

    def close(self):
        pass


class NotebookLMEngine(AnswerEngine):
    """NotebookLM qua notebooklm-py. Auth = storage_state.json (notebooklm login).

    store (SourceStore) dùng để map reference.source_id → tài liệu Lark khi trả lời.
    """

    def __init__(self, notebook_id, auth_path=None, store=None,
                 max_retries=2, retry_wait=15, op_timeout=300):
        self.notebook_id = notebook_id
        self.auth_path = auth_path
        self.store = store
        self.max_retries = max_retries
        self.retry_wait = retry_wait
        self.op_timeout = op_timeout
        self._loop = None
        self._client = None
        self._lock = PriorityLock()   # chat ưu tiên hơn sync

    # ---- async runtime (loop nền + client dùng chung) ----

    def _ensure_loop(self):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever, daemon=True,
                             name="nlm-engine-loop").start()
        return self._loop

    def _run(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        return fut.result(timeout=self.op_timeout)

    async def _get_client(self):
        if self._client is None:
            from pathlib import Path
            from notebooklm import AuthTokens, NotebookLMClient
            auth = await AuthTokens.from_storage(
                Path(self.auth_path) if self.auth_path else None)
            self._client = await NotebookLMClient(auth).__aenter__()
        return self._client

    async def _retry(self, op):
        from notebooklm import RateLimitError, NetworkError, ServerError
        last = None
        for i in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                return await op(client)
            except (RateLimitError, NetworkError, ServerError) as e:
                last = e
                if i < self.max_retries:
                    await asyncio.sleep(self.retry_wait * (i + 1))
        raise last

    def close(self):
        if self._client is not None:
            c, self._client = self._client, None
            self._run(c.__aexit__(None, None, None))

    # ---- hỏi đáp ----

    def ask(self, question, conversation_id=None) -> EngineAnswer:
        with self._lock.high():
            try:
                res = self._run(self._retry(
                    lambda c: c.chat.ask(self.notebook_id, question,
                                         conversation_id=conversation_id)))
            except Exception as e:  # degrade rõ ràng, không nổ lên consumer
                return EngineAnswer(ok=False, error=f"{type(e).__name__}: {e}")
        cites, seen = [], set()
        for ref in res.references or []:
            if ref.source_id in seen:
                continue
            seen.add(ref.source_id)
            row = self.store.by_nlm_source(ref.source_id) if self.store else None
            if row:
                cites.append(Citation(title=row["title"], url=row["lark_url"],
                                      snippet=(ref.cited_text or "")[:200]))
            else:
                # nguồn không có trong mapping (không phải tài liệu Lark đã sync)
                cites.append(Citation(title=f"Nguồn #{ref.citation_number or '?'}",
                                      url="", snippet=(ref.cited_text or "")[:200]))
        return EngineAnswer(ok=True, text=res.answer, citations=cites,
                            conversation_id=res.conversation_id or "")

    def configure_chat(self, custom_prompt):
        """Cài persona/format trả lời cho notebook (chạy 1 lần lúc khởi động).

        goal=CUSTOM là bắt buộc — thiếu nó NotebookLM bỏ qua custom_prompt.
        """
        from notebooklm import ChatGoal
        with self._lock.low():
            self._run(self._retry(
                lambda c: c.chat.configure(self.notebook_id, goal=ChatGoal.CUSTOM,
                                           custom_prompt=custom_prompt)))

    # ---- quản lý source (dùng bởi sync worker) ----

    def add_text_source(self, title, content) -> str:
        with self._lock.low():
            src = self._run(self._retry(
                lambda c: c.sources.add_text(self.notebook_id, title, content,
                                             wait=True)))
        return src.id

    def add_file_source(self, title, file_path) -> str:
        with self._lock.low():
            src = self._run(self._retry(
                lambda c: c.sources.add_file(self.notebook_id, file_path,
                                             title=title, wait=True)))
        return src.id

    def delete_source(self, source_id):
        from notebooklm import SourceNotFoundError
        with self._lock.low():
            try:
                self._run(self._retry(
                    lambda c: c.sources.delete(self.notebook_id, source_id)))
            except SourceNotFoundError:
                pass  # đã mất từ trước — coi như xoá xong

    def list_source_ids(self) -> list:
        with self._lock.low():
            srcs = self._run(self._retry(
                lambda c: c.sources.list(self.notebook_id)))
        return [s.id for s in srcs]
