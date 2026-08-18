# Bot ANN_KHHH / PLANNING' ASSISTANT — chạy 24/7, không phụ thuộc máy cá nhân.
FROM python:3.11-slim

WORKDIR /agent

# Cài trước, tách layer để đổi code không phải cài lại.
RUN pip install --no-cache-dir requests pyyaml python-dotenv openpyxl

COPY src/ src/
COPY tests/ tests/
COPY config/ config/
COPY knowledge/ knowledge/
COPY docker-entrypoint.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && cd src && python ../tests/test_coc.py     # build fail nếu tra cứu CoC lỗi

WORKDIR /agent/src
ENTRYPOINT ["docker-entrypoint.sh"]
