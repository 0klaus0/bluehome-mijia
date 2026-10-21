FROM python:3.12-slim

WORKDIR /opt/bluehome
COPY server/requirements.txt /opt/bluehome/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server /opt/bluehome/server
COPY web /opt/bluehome/web
ENV BLUEHOME_DATA_DIR=/data BLUEHOME_NO_BROWSER=1 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 4174
CMD ["python", "server/connect_mijia.py", "--lan"]
