#!/usr/bin/env python3

"""
Unit tests for the hospital management application.
Tests cover all API endpoints and business logic validation.
"""

import fakeredis
from unittest.mock import patch
from tornado.testing import AsyncHTTPTestCase
import main


class TestApplication(AsyncHTTPTestCase):
    """Base test class for the application."""

    def setUp(self):
        """Set up test fixtures before each test."""
        super().setUp()
        # Create a fake Redis instance for testing
        self.fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
        # Initialize database
        self.fake_redis.set("hospital:autoID", 1)
        self.fake_redis.set("doctor:autoID", 1)
        self.fake_redis.set("patient:autoID", 1)
        self.fake_redis.set("diagnosis:autoID", 1)
        self.fake_redis.set("db_initiated", 1)
        # Patch Redis connection to use fake Redis for all tests
        self.redis_patcher = patch('main.r', self.fake_redis)
        self.redis_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        self.redis_patcher.stop()
        super().tearDown()

    def get_app(self):
        """Create and return the Tornado application."""
        return main.make_app()


class TestMainHandler(TestApplication):
    """Tests for the main page handler."""

    def test_main_handler_get(self):
        """Test GET request to main page."""
        response = self.fetch("/")
        self.assertEqual(response.code, 200)
        # HTML может быть в любом регистре
        self.assertIn(b"<!doctype html>", response.body.lower())


class TestHospitalHandler(TestApplication):
    """Tests for HospitalHandler endpoints."""

    def test_hospital_get_empty(self):
        """Test GET request when no hospitals exist."""
        response = self.fetch("/hospital")
        self.assertEqual(response.code, 200)

    def test_hospital_get_with_data(self):
        """Test GET request when hospitals exist."""
        # Add a hospital to fake Redis
        self.fake_redis.set("hospital:autoID", 2)
        self.fake_redis.hset("hospital:0", mapping={
            b"name": b"Test Hospital",
            b"address": b"123 Test St",
            b"phone": b"123-456-7890",
            b"beds_number": b"100"
        })
        
        response = self.fetch("/hospital")
        self.assertEqual(response.code, 200)

    def test_hospital_post_success(self):
        """Test successful POST request to create a hospital."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=Test Hospital&address=123 Test St&beds_number=100&phone=123-456-7890"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)
        self.assertIn(b"Test Hospital", response.body)

    def test_hospital_post_missing_name(self):
        """Test POST request with missing name field."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="address=123 Test St&beds_number=100&phone=123-456-7890"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_hospital_post_missing_address(self):
        """Test POST request with missing address field."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=Test Hospital&beds_number=100&phone=123-456-7890"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_hospital_post_empty_name(self):
        """Test POST request with empty name field."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=&address=123 Test St&beds_number=100&phone=123-456-7890"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"Hospital name and address required", response.body)

    def test_hospital_post_empty_address(self):
        """Test POST request with empty address field."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=Test Hospital&address=&beds_number=100&phone=123-456-7890"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"Hospital name and address required", response.body)

    def test_hospital_post_all_fields(self):
        """Test POST request with all fields provided."""
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=City Hospital&address=456 Main St&beds_number=250&phone=555-1234"
        )
        self.assertEqual(response.code, 200)
        # Verify data was stored
        hospital_data = self.fake_redis.hgetall("hospital:1")
        self.assertEqual(hospital_data[b"name"], b"City Hospital")
        self.assertEqual(hospital_data[b"address"], b"456 Main St")
        self.assertEqual(hospital_data[b"beds_number"], b"250")
        self.assertEqual(hospital_data[b"phone"], b"555-1234")


class TestDoctorHandler(TestApplication):
    """Tests for DoctorHandler endpoints."""

    def test_doctor_get_empty(self):
        """Test GET request when no doctors exist."""
        response = self.fetch("/doctor")
        self.assertEqual(response.code, 200)

    def test_doctor_get_with_data(self):
        """Test GET request when doctors exist."""
        self.fake_redis.set("doctor:autoID", 2)
        self.fake_redis.hset("doctor:0", mapping={
            b"surname": b"Smith",
            b"profession": b"Cardiologist",
            b"hospital_ID": b"0"
        })
        
        response = self.fetch("/doctor")
        self.assertEqual(response.code, 200)

    def test_doctor_post_success(self):
        """Test successful POST request to create a doctor."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Smith&profession=Cardiologist&hospital_ID="
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)
        self.assertIn(b"Smith", response.body)

    def test_doctor_post_with_valid_hospital_id(self):
        """Test POST request with valid hospital ID."""
        # First create a hospital
        self.fake_redis.set("hospital:autoID", 2)
        self.fake_redis.hset("hospital:0", mapping={
            b"name": b"Test Hospital",
            b"address": b"123 Test St",
            b"phone": b"123-456-7890",
            b"beds_number": b"100"
        })
        
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Johnson&profession=Surgeon&hospital_ID=0"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)

    def test_doctor_post_missing_surname(self):
        """Test POST request with missing surname."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="profession=Cardiologist&hospital_ID="
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_doctor_post_missing_profession(self):
        """Test POST request with missing profession."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Smith&hospital_ID="
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_doctor_post_invalid_hospital_id(self):
        """Test POST request with non-existent hospital ID."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Smith&profession=Cardiologist&hospital_ID=999"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"No hospital with such ID", response.body)

    def test_doctor_post_empty_surname(self):
        """Test POST request with empty surname."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=&profession=Cardiologist&hospital_ID="
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"Surname and profession required", response.body)


class TestPatientHandler(TestApplication):
    """Tests for PatientHandler endpoints."""

    def test_patient_get_empty(self):
        """Test GET request when no patients exist."""
        response = self.fetch("/patient")
        self.assertEqual(response.code, 200)

    def test_patient_get_with_data(self):
        """Test GET request when patients exist."""
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        response = self.fetch("/patient")
        self.assertEqual(response.code, 200)

    def test_patient_post_success_male(self):
        """Test successful POST request to create a male patient."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&born_date=1990-01-01&sex=M&mpn=123456789"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)
        self.assertIn(b"Doe", response.body)

    def test_patient_post_success_female(self):
        """Test successful POST request to create a female patient."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Jane&born_date=1985-05-15&sex=F&mpn=987654321"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)

    def test_patient_post_missing_surname(self):
        """Test POST request with missing surname."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="born_date=1990-01-01&sex=M&mpn=123456789"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_patient_post_missing_born_date(self):
        """Test POST request with missing born_date."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&sex=M&mpn=123456789"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_patient_post_missing_sex(self):
        """Test POST request with missing sex."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&born_date=1990-01-01&mpn=123456789"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_patient_post_missing_mpn(self):
        """Test POST request with missing mpn."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&born_date=1990-01-01&sex=M"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_patient_post_invalid_sex(self):
        """Test POST request with invalid sex value."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&born_date=1990-01-01&sex=X&mpn=123456789"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"Sex must be 'M' or 'F'", response.body)

    def test_patient_post_invalid_sex_lowercase(self):
        """Test POST request with lowercase sex value."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Doe&born_date=1990-01-01&sex=m&mpn=123456789"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"Sex must be 'M' or 'F'", response.body)

    def test_patient_post_empty_fields(self):
        """Test POST request with empty fields."""
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=&born_date=&sex=&mpn="
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"All fields required", response.body)


class TestDiagnosisHandler(TestApplication):
    """Tests for DiagnosisHandler endpoints."""

    def test_diagnosis_get_empty(self):
        """Test GET request when no diagnoses exist."""
        response = self.fetch("/diagnosis")
        self.assertEqual(response.code, 200)

    def test_diagnosis_get_with_data(self):
        """Test GET request when diagnoses exist."""
        # First create a patient
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        self.fake_redis.set("diagnosis:autoID", 2)
        self.fake_redis.hset("diagnosis:0", mapping={
            b"patient_ID": b"0",
            b"type": b"Flu",
            b"information": b"Common cold symptoms"
        })
        
        response = self.fetch("/diagnosis")
        self.assertEqual(response.code, 200)

    def test_diagnosis_post_success(self):
        """Test successful POST request to create a diagnosis."""
        # First create a patient
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="patient_ID=0&type=Flu&information=Common cold symptoms"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: ID 1", response.body)
        self.assertIn(b"Doe", response.body)

    def test_diagnosis_post_missing_patient_id(self):
        """Test POST request with missing patient_ID."""
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="type=Flu&information=Common cold symptoms"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_diagnosis_post_missing_type(self):
        """Test POST request with missing type."""
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="patient_ID=0&information=Common cold symptoms"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_diagnosis_post_invalid_patient_id(self):
        """Test POST request with non-existent patient ID."""
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="patient_ID=999&type=Flu&information=Common cold symptoms"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"No patient with such ID", response.body)

    def test_diagnosis_post_with_empty_information(self):
        """Test POST request with empty information field (should be allowed)."""
        # First create a patient
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="patient_ID=0&type=Flu&information="
        )
        self.assertEqual(response.code, 200)


class TestDoctorPatientHandler(TestApplication):
    """Tests for DoctorPatientHandler endpoints."""

    def test_doctor_patient_get_empty(self):
        """Test GET request when no doctor-patient relationships exist."""
        response = self.fetch("/doctor-patient")
        self.assertEqual(response.code, 200)

    def test_doctor_patient_get_with_data(self):
        """Test GET request when doctor-patient relationships exist."""
        self.fake_redis.set("doctor:autoID", 2)
        self.fake_redis.hset("doctor:0", mapping={
            b"surname": b"Smith",
            b"profession": b"Cardiologist",
            b"hospital_ID": b"0"
        })
        self.fake_redis.sadd("doctor-patient:0", "1")
        
        response = self.fetch("/doctor-patient")
        self.assertEqual(response.code, 200)

    def test_doctor_patient_post_success(self):
        """Test successful POST request to link doctor and patient."""
        # Create a doctor
        self.fake_redis.set("doctor:autoID", 2)
        self.fake_redis.hset("doctor:0", mapping={
            b"surname": b"Smith",
            b"profession": b"Cardiologist",
            b"hospital_ID": b"0"
        })
        
        # Create a patient
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        response = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=0&patient_ID=0"
        )
        self.assertEqual(response.code, 200)
        self.assertIn(b"OK: doctor ID: 0", response.body)
        self.assertIn(b"patient ID: 0", response.body)
        
        # Verify relationship was stored
        patients = self.fake_redis.smembers("doctor-patient:0")
        self.assertIn(b"0", patients)

    def test_doctor_patient_post_missing_doctor_id(self):
        """Test POST request with missing doctor_ID."""
        response = self.fetch(
            "/doctor-patient",
            method="POST",
            body="patient_ID=0"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_doctor_patient_post_missing_patient_id(self):
        """Test POST request with missing patient_ID."""
        response = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=0"
        )
        self.assertEqual(response.code, 400)
        # Tornado throws MissingArgumentError when argument is missing
        self.assertIn(b"Missing argument", response.body)

    def test_doctor_patient_post_invalid_doctor_id(self):
        """Test POST request with non-existent doctor ID."""
        # Create a patient but no doctor
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        response = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=999&patient_ID=0"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"No such ID for doctor or patient", response.body)

    def test_doctor_patient_post_invalid_patient_id(self):
        """Test POST request with non-existent patient ID."""
        # Create a doctor but no patient
        self.fake_redis.set("doctor:autoID", 2)
        self.fake_redis.hset("doctor:0", mapping={
            b"surname": b"Smith",
            b"profession": b"Cardiologist",
            b"hospital_ID": b"0"
        })
        
        response = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=0&patient_ID=999"
        )
        self.assertEqual(response.code, 400)
        self.assertIn(b"No such ID for doctor or patient", response.body)

    def test_doctor_patient_post_multiple_patients(self):
        """Test linking multiple patients to the same doctor."""
        # Create a doctor
        self.fake_redis.set("doctor:autoID", 2)
        self.fake_redis.hset("doctor:0", mapping={
            b"surname": b"Smith",
            b"profession": b"Cardiologist",
            b"hospital_ID": b"0"
        })
        
        # Create two patients
        self.fake_redis.set("patient:autoID", 3)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        self.fake_redis.hset("patient:1", mapping={
            b"surname": b"Jane",
            b"born_date": b"1985-05-15",
            b"sex": b"F",
            b"mpn": b"987654321"
        })
        
        # Link first patient
        response1 = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=0&patient_ID=0"
        )
        self.assertEqual(response1.code, 200)
        
        # Link second patient
        response2 = self.fetch(
            "/doctor-patient",
            method="POST",
            body="doctor_ID=0&patient_ID=1"
        )
        self.assertEqual(response2.code, 200)
        
        # Verify both patients are linked
        patients = self.fake_redis.smembers("doctor-patient:0")
        self.assertIn(b"0", patients)
        self.assertIn(b"1", patients)


class TestDatabaseInitialization(TestApplication):
    """Tests for database initialization logic."""

    def test_init_db_creates_auto_ids(self):
        """Test that init_db creates all required autoID keys."""
        # Clear the fake Redis
        self.fake_redis.flushdb()
        
        # Call init_db (main.r is already patched in setUp)
        main.init_db()
        
        # Verify all autoID keys were created
        self.assertEqual(self.fake_redis.get("hospital:autoID"), b"1")
        self.assertEqual(self.fake_redis.get("doctor:autoID"), b"1")
        self.assertEqual(self.fake_redis.get("patient:autoID"), b"1")
        self.assertEqual(self.fake_redis.get("diagnosis:autoID"), b"1")
        self.assertEqual(self.fake_redis.get("db_initiated"), b"1")

    def test_init_db_idempotent(self):
        """Test that init_db doesn't overwrite existing data."""
        # Set up existing data
        self.fake_redis.set("hospital:autoID", 5)
        self.fake_redis.set("doctor:autoID", 3)
        self.fake_redis.set("patient:autoID", 10)
        self.fake_redis.set("diagnosis:autoID", 2)
        self.fake_redis.set("db_initiated", 1)
        
        # Call init_db (main.r is already patched in setUp)
        main.init_db()
        
        # Verify existing values were preserved
        self.assertEqual(self.fake_redis.get("hospital:autoID"), b"5")
        self.assertEqual(self.fake_redis.get("doctor:autoID"), b"3")
        self.assertEqual(self.fake_redis.get("patient:autoID"), b"10")
        self.assertEqual(self.fake_redis.get("diagnosis:autoID"), b"2")


class TestEdgeCases(TestApplication):
    """Tests for edge cases and boundary conditions."""

    def test_hospital_auto_id_increment(self):
        """Test that hospital autoID increments correctly."""
        initial_id = int(self.fake_redis.get("hospital:autoID"))
        
        response = self.fetch(
            "/hospital",
            method="POST",
            body="name=Hospital1&address=Address1&beds_number=100&phone=123"
        )
        self.assertEqual(response.code, 200)
        
        new_id = int(self.fake_redis.get("hospital:autoID"))
        self.assertEqual(new_id, initial_id + 1)

    def test_doctor_auto_id_increment(self):
        """Test that doctor autoID increments correctly."""
        initial_id = int(self.fake_redis.get("doctor:autoID"))
        
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Doctor1&profession=Surgeon&hospital_ID="
        )
        self.assertEqual(response.code, 200)
        
        new_id = int(self.fake_redis.get("doctor:autoID"))
        self.assertEqual(new_id, initial_id + 1)

    def test_patient_auto_id_increment(self):
        """Test that patient autoID increments correctly."""
        initial_id = int(self.fake_redis.get("patient:autoID"))
        
        response = self.fetch(
            "/patient",
            method="POST",
            body="surname=Patient1&born_date=1990-01-01&sex=M&mpn=123"
        )
        self.assertEqual(response.code, 200)
        
        new_id = int(self.fake_redis.get("patient:autoID"))
        self.assertEqual(new_id, initial_id + 1)

    def test_diagnosis_auto_id_increment(self):
        """Test that diagnosis autoID increments correctly."""
        # Create a patient first
        self.fake_redis.set("patient:autoID", 2)
        self.fake_redis.hset("patient:0", mapping={
            b"surname": b"Doe",
            b"born_date": b"1990-01-01",
            b"sex": b"M",
            b"mpn": b"123456789"
        })
        
        initial_id = int(self.fake_redis.get("diagnosis:autoID"))
        
        response = self.fetch(
            "/diagnosis",
            method="POST",
            body="patient_ID=0&type=Flu&information=Test"
        )
        self.assertEqual(response.code, 200)
        
        new_id = int(self.fake_redis.get("diagnosis:autoID"))
        self.assertEqual(new_id, initial_id + 1)

    def test_hospital_get_with_gaps_in_ids(self):
        """Test GET request when there are gaps in hospital IDs."""
        self.fake_redis.set("hospital:autoID", 5)
        # Only create hospitals at indices 0 and 3
        self.fake_redis.hset("hospital:0", mapping={
            b"name": b"Hospital 0",
            b"address": b"Address 0",
            b"phone": b"123",
            b"beds_number": b"100"
        })
        self.fake_redis.hset("hospital:3", mapping={
            b"name": b"Hospital 3",
            b"address": b"Address 3",
            b"phone": b"456",
            b"beds_number": b"200"
        })
        
        response = self.fetch("/hospital")
        self.assertEqual(response.code, 200)

    def test_doctor_with_empty_hospital_id(self):
        """Test creating doctor with empty hospital_ID (should be allowed)."""
        response = self.fetch(
            "/doctor",
            method="POST",
            body="surname=Smith&profession=Cardiologist&hospital_ID="
        )
        self.assertEqual(response.code, 200)
        
        # Verify doctor was created with empty hospital_ID
        doctor_data = self.fake_redis.hgetall("doctor:1")
        self.assertEqual(doctor_data[b"hospital_ID"], b"")

