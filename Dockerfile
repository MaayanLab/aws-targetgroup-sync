FROM python:3.8

ADD requirements.txt requirements.txt
RUN set -x \
  && pip3 install --no-cache-dir -r requirements.txt \
  && rm requirements.txt

ADD aws-targetgroup-sync.py aws-targetgroup-sync.py
RUN set -x \
  && chmod +x aws-targetgroup-sync.py

CMD ./aws-targetgroup-sync.py