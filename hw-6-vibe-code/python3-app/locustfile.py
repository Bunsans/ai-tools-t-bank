#!/usr/bin/env python3
"""
Locust load testing script for Hospital Management Application.

This script simulates realistic user behavior with gradual load increase
from 0 to 100 users, testing all major endpoints of the application.
"""

import logging
import random

from locust import HttpUser, LoadTestShape, between, events, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HospitalUser(HttpUser):
    """
    Simulates a user interacting with the hospital management system.

    Wait time between tasks: 1-3 seconds (simulates real user behavior)
    """

    wait_time = between(1, 3)

    def on_start(self):
        """
        Called when a user starts. Used to initialize data that will be
        used throughout the user's session.
        """
        # Store IDs for created entities to use in relationships
        self.hospital_ids = []
        self.doctor_ids = []
        self.patient_ids = []
        logger.info(f"New user started: {id(self)}")

    @task(10)
    def view_main_page(self):
        """
        Task: View the main page (highest weight - most frequent action).
        Weight: 10 (executed most often)
        """
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Main page returned {response.status_code}")

    @task(5)
    def view_hospitals(self):
        """
        Task: View the list of hospitals.
        Weight: 5
        """
        with self.client.get("/hospital", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Hospital list returned {response.status_code}")

    @task(3)
    def create_hospital(self):
        """
        Task: Create a new hospital.
        Weight: 3 (less frequent than viewing)
        """
        hospital_data = {
            "name": f"Test Hospital {random.randint(1000, 9999)}",
            "address": f"{random.randint(1, 999)} Test Street",
            "beds_number": str(random.randint(50, 500)),
            "phone": f"+1-555-{random.randint(1000, 9999)}",
        }

        with self.client.post(
            "/hospital", data=hospital_data, catch_response=True
        ) as response:
            if response.status_code == 200 and b"OK: ID" in response.content:
                # Extract ID from response if needed
                response.success()
                logger.debug(f"Created hospital: {hospital_data['name']}")
            else:
                response.failure(f"Hospital creation failed: {response.status_code}")

    @task(5)
    def view_doctors(self):
        """
        Task: View the list of doctors.
        Weight: 5
        """
        with self.client.get("/doctor", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Doctor list returned {response.status_code}")

    @task(3)
    def create_doctor(self):
        """
        Task: Create a new doctor.
        Weight: 3
        """
        surnames = [
            "Smith",
            "Johnson",
            "Williams",
            "Brown",
            "Jones",
            "Garcia",
            "Miller",
        ]
        professions = [
            "Cardiologist",
            "Surgeon",
            "Pediatrician",
            "Neurologist",
            "Oncologist",
        ]

        doctor_data = {
            "surname": random.choice(surnames),
            "profession": random.choice(professions),
            "hospital_ID": "",  # Empty for simplicity, can be populated if tracking IDs
        }

        with self.client.post(
            "/doctor", data=doctor_data, catch_response=True
        ) as response:
            if response.status_code == 200 and b"OK: ID" in response.content:
                response.success()
                logger.debug(f"Created doctor: {doctor_data['surname']}")
            else:
                response.failure(f"Doctor creation failed: {response.status_code}")

    @task(5)
    def view_patients(self):
        """
        Task: View the list of patients.
        Weight: 5
        """
        with self.client.get("/patient", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Patient list returned {response.status_code}")

    @task(4)
    def create_patient(self):
        """
        Task: Create a new patient.
        Weight: 4
        """
        surnames = ["Doe", "Jane", "Anderson", "Taylor", "Thomas", "Moore", "Martin"]

        patient_data = {
            "surname": random.choice(surnames),
            "born_date": f"{random.randint(1950, 2010)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "sex": random.choice(["M", "F"]),
            "mpn": str(random.randint(100000000, 999999999)),
        }

        with self.client.post(
            "/patient", data=patient_data, catch_response=True
        ) as response:
            if response.status_code == 200 and b"OK: ID" in response.content:
                response.success()
                logger.debug(f"Created patient: {patient_data['surname']}")
            else:
                response.failure(f"Patient creation failed: {response.status_code}")

    @task(3)
    def view_diagnoses(self):
        """
        Task: View the list of diagnoses.
        Weight: 3
        """
        with self.client.get("/diagnosis", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Diagnosis list returned {response.status_code}")

    @task(2)
    def view_doctor_patient_relations(self):
        """
        Task: View doctor-patient relationships.
        Weight: 2 (least frequent read operation)
        """
        with self.client.get("/doctor-patient", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Doctor-patient list returned {response.status_code}")


# Custom load shape for gradual increase to 100 users
class GradualLoadShape(LoadTestShape):
    """
    Custom load shape that gradually increases users from 0 to 100 over 5 minutes,
    holds at 100 for 3 minutes, then gradually decreases.

    Timeline:
    - 0-5 min: Ramp up from 0 to 100 users
    - 5-8 min: Hold at 100 users (peak load)
    - 8-10 min: Ramp down to 0 users
    """

    stages = [
        # (duration_seconds, target_user_count, spawn_rate)
        {"duration": 60, "users": 20, "spawn_rate": 1},  # 0-1 min: 20 users
        {"duration": 120, "users": 40, "spawn_rate": 1},  # 1-2 min: 40 users
        {"duration": 180, "users": 60, "spawn_rate": 1},  # 2-3 min: 60 users
        {"duration": 240, "users": 80, "spawn_rate": 1},  # 3-4 min: 80 users
        {"duration": 300, "users": 100, "spawn_rate": 1},  # 4-5 min: 100 users (peak)
        {"duration": 480, "users": 100, "spawn_rate": 0},  # 5-8 min: Hold at 100
        {"duration": 540, "users": 50, "spawn_rate": 2},  # 8-9 min: Down to 50
        {"duration": 600, "users": 0, "spawn_rate": 2},  # 9-10 min: Down to 0
    ]

    def tick(self):
        """
        Returns a tuple with the current number of users and spawn rate.
        Called approximately once per second during the test.
        """
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])

        return None  # Test is complete


# Event listeners for custom metrics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts."""
    logger.info("=" * 60)
    logger.info("LOAD TEST STARTED")
    logger.info("Target: Hospital Management Application")
    logger.info("Max Users: 100")
    logger.info("Duration: ~10 minutes")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops."""
    logger.info("=" * 60)
    logger.info("LOAD TEST COMPLETED")
    logger.info("Check the web UI or generated reports for detailed metrics")
    logger.info("=" * 60)


# Optional: Add custom metrics tracking
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """
    Called for each request. Can be used for custom logging or metrics.
    """
    if exception:
        logger.error(f"Request failed: {name} - {exception}")
    elif response_time > 1000:  # Log slow requests (> 1 second)
        logger.warning(f"Slow request detected: {name} - {response_time}ms")
