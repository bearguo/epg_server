FROM frolvlad/alpine-python3:latest

WORKDIR /app/

COPY requirements.txt /app/

COPY epg.py /app/

COPY epg.conf /app/conf/

RUN pip install -r /app/requirements.txt

RUN apk add --no-cache curl

HEALTHCHECK --interval=5s --timeout=3s CMD curl -fs http://localhost:10010/EPG/channel || exit 1

EXPOSE 10010

CMD ["python", "epg.py"]
