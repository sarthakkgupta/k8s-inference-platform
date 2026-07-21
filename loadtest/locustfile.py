"""Locust load test for the inference service.

Run standalone (see Makefile `loadtest` target):
    locust -f loadtest/locustfile.py --host http://localhost:8080 \
        --headless -u 50 -r 10 -t 2m
"""
import random

from locust import HttpUser, task, between

SAMPLE_TEXTS = [
    "I absolutely love this product, it's amazing!",
    "This is the worst experience I've ever had.",
    "The service was okay, nothing special.",
    "Fantastic support team, very happy with the outcome.",
    "Terrible quality, I want a refund.",
    "It works as expected, no complaints.",
]


class InferenceUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def predict(self):
        payload = {"text": random.choice(SAMPLE_TEXTS)}
        self.client.post("/predict", json=payload)

    @task(1)
    def healthz(self):
        self.client.get("/healthz")
