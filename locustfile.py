from locust import HttpUser, between, task


class FlashSaleUser(HttpUser):
    wait_time = between(0, 0.005)

    @task
    def check_health(self):
        self.client.get("/health", name="/health")

    @task(3)
    def read_product(self):
        self.client.get("/api/products/1", name="/api/products/{id}")

    @task(2)
    def place_order(self):
        with self.client.post(
            "/api/orders",
            json={"product_id": 1, "quantity": 1},
            name="/api/orders",
            catch_response=True,
        ) as response:
            if response.status_code in (201, 409):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")
