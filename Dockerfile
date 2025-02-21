FROM public.ecr.aws/docker/library/python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
RUN pip install pytest pytest-mock
RUN pytest -v
CMD ["python", "app.py"]