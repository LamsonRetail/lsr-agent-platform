# Hướng Dẫn Push Lên GitHub

5 commits đã sẵn sàng trên nhánh `agent/pmo-AG-PMO`. Để push:

## Cách 1: SSH Key (Recommended)

```bash
# 1. Thêm public key vào GitHub
#    Vào https://github.com/settings/keys
#    Click "New SSH key"
#    Paste nội dung:
cat ~/.ssh/id_ed25519_lsr-agent-platform.pub

# 2. Rồi push
cd ~/Desktop/lsr-agent-platform
git push -u origin agent/pmo-AG-PMO
```

## Cách 2: HTTPS với Personal Token

```bash
cd ~/Desktop/lsr-agent-platform
git remote set-url origin https://github.com/LamsonRetail/lsr-agent-platform.git

# Khi được hỏi username + password:
# Username: <your-github-username>
# Password: <github-personal-access-token>
#
# Lấy token tại: https://github.com/settings/tokens
# Scope cần: repo (read+write)

git push -u origin agent/pmo-AG-PMO
```

## Cách 3: Tạo Pull Request Từ Web

```bash
# Vào https://github.com/LamsonRetail/lsr-agent-platform
# Click "Compare & pull request" (GitHub tự phát hiện branch mới)
# Hoặc tạo PR thủ công:
#   Base: main
#   Compare: agent/pmo-AG-PMO
```

## Sau Khi Push

Tạo PR và yêu cầu review trước merge vào `main`:

```markdown
**Tiêu đề:** AG-PMO: Agent trợ lý PMO cho LamsonRetail

**Mô tả:**
- Giai đoạn 0 (GĐ0): Tra dữ liệu dự án từ Lark Base
- Trả lời: hiện trạng, rủi ro, vướng mắc, việc kế tiếp
- Chặn: xin quyết định, ngoài phạm vi, dữ liệu tài chính mật
- Test: 12/12 case pass

**Commits:**
- a22149f — Scaffold + USECASE.md + TESTCASES.md
- a997fb8 — USECASE.md từ dữ liệu Lark thật
- 10e0e1c — lark_read.py + pmo_data.py + pmo_answer.py + consumer logic
- 76c3add — run_test.sh: test trực tiếp, 12/12 pass
- 29c958d — SETUP.md + hướng dẫn test

**Test:**
```bash
cd agents/AG-PMO
export $(cat .env.local | xargs)  # Điền LARK credentials
./run_test.sh                      # 12/12 pass
```

**Chú ý:**
- GĐ1+ (biên bản họp, lời mời, tri thức) chưa làm, chờ console access
- Scope-guard, agent-gate đều pass
```
