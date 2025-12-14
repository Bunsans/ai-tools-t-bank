#!/usr/bin/env python3
"""
Hospital Management Application

A Tornado-based web application for managing hospitals, doctors, patients,
diagnoses, and doctor-patient relationships using Redis as the data store.
"""

import logging
import os
import redis
import tornado.ioloop
import tornado.web

from tornado.options import parse_command_line

# Configuration constants
PORT = 8888
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

# Redis key prefixes
KEY_PREFIX_HOSPITAL = "hospital:"
KEY_PREFIX_DOCTOR = "doctor:"
KEY_PREFIX_PATIENT = "patient:"
KEY_PREFIX_DIAGNOSIS = "diagnosis:"
KEY_PREFIX_DOCTOR_PATIENT = "doctor-patient:"
KEY_AUTO_ID_HOSPITAL = "hospital:autoID"
KEY_AUTO_ID_DOCTOR = "doctor:autoID"
KEY_AUTO_ID_PATIENT = "patient:autoID"
KEY_AUTO_ID_DIAGNOSIS = "diagnosis:autoID"
KEY_DB_INITIATED = "db_initiated"

# Valid sex values for patients
VALID_SEX_VALUES = ['M', 'F']

# Error messages
ERROR_REDIS_CONNECTION = "Redis connection refused"
ERROR_SOMETHING_WRONG = "Something went terribly wrong"

# Initialize Redis connection
r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)


class BaseRedisHandler(tornado.web.RequestHandler):
    """
    Base handler class providing common Redis operations and error handling.
    
    This class encapsulates common patterns used across all entity handlers:
    - Retrieving all entities of a type
    - Handling Redis connection errors
    - Creating new entities with validation
    """
    
    def get_redis_connection(self):
        """
        Get the Redis connection instance.
        
        Returns:
            redis.StrictRedis: The Redis connection object
        """
        return r
    
    def handle_redis_error(self, error):
        """
        Handle Redis connection errors consistently.
        
        Args:
            error: The exception that occurred
            
        Sets HTTP 400 status and writes error message to response.
        """
        self.set_status(400)
        self.write(ERROR_REDIS_CONNECTION)
        logging.error(f"Redis connection error: {error}")
    
    def get_all_entities(self, entity_prefix, auto_id_key):
        """
        Retrieve all entities of a given type from Redis.
        
        This method iterates through all IDs from 0 to the current autoID value
        and collects all non-empty hash records.
        
        Args:
            entity_prefix (str): Redis key prefix for the entity type (e.g., "hospital:")
            auto_id_key (str): Redis key for the auto-incrementing ID (e.g., "hospital:autoID")
            
        Returns:
            list: List of dictionaries containing entity data, or empty list on error
            
        Note:
            This approach is O(n) where n is the current autoID value. For better
            performance with large datasets, consider using Redis Sets to track
            existing entity IDs.
        """
        items = []
        try:
            redis_conn = self.get_redis_connection()
            auto_id_bytes = redis_conn.get(auto_id_key)
            
            if not auto_id_bytes:
                return items
            
            max_id = int(auto_id_bytes.decode())
            
            for i in range(max_id):
                entity_key = f"{entity_prefix}{i}"
                result = redis_conn.hgetall(entity_key)
                if result:
                    items.append(result)
                    
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
            return []
        except (ValueError, AttributeError) as e:
            logging.error(f"Error decoding autoID for {entity_prefix}: {e}")
            self.set_status(500)
            self.write(ERROR_SOMETHING_WRONG)
            return []
            
        return items
    
    def get_next_id(self, auto_id_key):
        """
        Get the next available ID for an entity type and increment the counter.
        
        Args:
            auto_id_key (str): Redis key for the auto-incrementing ID
            
        Returns:
            str: The ID to use for the new entity (as string)
            
        Raises:
            redis.exceptions.ConnectionError: If Redis connection fails
            ValueError: If autoID cannot be decoded
        """
        redis_conn = self.get_redis_connection()
        current_id_bytes = redis_conn.get(auto_id_key)
        
        if not current_id_bytes:
            raise ValueError(f"AutoID key {auto_id_key} not found")
        
        current_id = current_id_bytes.decode()
        redis_conn.incr(auto_id_key)
        return current_id
    
    def create_entity(self, entity_key, fields_dict, expected_field_count):
        """
        Create a new entity in Redis using a hash structure.
        
        Uses Redis pipeline for atomic batch operations to ensure all fields
        are set together or not at all.
        
        Args:
            entity_key (str): Full Redis key for the entity (e.g., "hospital:1")
            fields_dict (dict): Dictionary mapping field names to values
            expected_field_count (int): Expected number of fields to be set
            
        Returns:
            bool: True if all fields were set successfully, False otherwise
        """
        try:
            redis_conn = self.get_redis_connection()
            
            # Use pipeline for atomic batch operations
            pipe = redis_conn.pipeline()
            for field_name, field_value in fields_dict.items():
                pipe.hset(entity_key, field_name, field_value)
            results = pipe.execute()
            
            # Count successful operations (hset returns 1 for new field, 0 for existing)
            # Sum should equal expected_field_count if all fields are new
            total_operations = sum(results)
            
            # Note: hset returns 1 for new fields, 0 for updates
            # We check if we got the expected number of operations
            # In practice, this validates that all fields were processed
            return total_operations >= expected_field_count
            
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
            return False
        except Exception as e:
            logging.error(f"Error creating entity {entity_key}: {e}")
            return False
    
    def check_entity_exists(self, entity_key):
        """
        Check if an entity exists in Redis.
        
        Args:
            entity_key (str): Full Redis key for the entity
            
        Returns:
            bool: True if entity exists, False otherwise
        """
        try:
            redis_conn = self.get_redis_connection()
            result = redis_conn.hgetall(entity_key)
            return bool(result)
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
            return False
    
    def _handle_value_error(self, error):
        """
        Handle value errors (e.g., decoding issues).
        
        Args:
            error: The exception that occurred
        """
        self.set_status(500)
        self.write(ERROR_SOMETHING_WRONG)
        logging.error(f"Value error: {error}")


class MainHandler(tornado.web.RequestHandler):
    """
    Handler for the main page.
    
    Renders the index.html template.
    """
    
    def get(self):
        """Render the main index page."""
        self.render('templates/index.html')


class HospitalHandler(BaseRedisHandler):
    """
    Handler for hospital-related operations.
    
    Supports:
    - GET: Retrieve list of all hospitals
    - POST: Create a new hospital with name, address, beds_number, and phone
    """
    
    # Expected number of fields for a hospital entity
    HOSPITAL_FIELD_COUNT = 4
    
    def get(self):
        """
        Retrieve and display all hospitals.
        
        Renders the hospital.html template with a list of all hospital records.
        """
        items = self.get_all_entities(KEY_PREFIX_HOSPITAL, KEY_AUTO_ID_HOSPITAL)
        
        # Only render if we didn't encounter an error (items would be empty list on error)
        if self.get_status() != 400:
            self.render('templates/hospital.html', items=items)

    def post(self):
        """
        Create a new hospital.
        
        Required fields:
        - name: Hospital name
        - address: Hospital address
        
        Optional fields:
        - beds_number: Number of beds
        - phone: Contact phone number
        
        Returns:
            Success message with hospital ID, or error message on failure
        """
        name = self.get_argument('name')
        address = self.get_argument('address')
        beds_number = self.get_argument('beds_number')
        phone = self.get_argument('phone')

        # Validate required fields
        if not name or not address:
            self.set_status(400)
            self.write("Hospital name and address required")
            return

        logging.debug(f"Hospital creation: name={name}, address={address}, beds={beds_number}, phone={phone}")

        try:
            # Get next available ID
            entity_id = self.get_next_id(KEY_AUTO_ID_HOSPITAL)
            entity_key = f"{KEY_PREFIX_HOSPITAL}{entity_id}"
            
            # Prepare fields dictionary
            fields = {
                "name": name,
                "address": address,
                "phone": phone,
                "beds_number": beds_number
            }
            
            # Create entity using batch operation
            success = self.create_entity(entity_key, fields, self.HOSPITAL_FIELD_COUNT)
            
            if success:
                self.write(f'OK: ID {entity_id} for {name}')
            else:
                self.set_status(500)
                self.write(ERROR_SOMETHING_WRONG)
                
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
        except ValueError as e:
            self._handle_value_error(e)


class DoctorHandler(BaseRedisHandler):
    """
    Handler for doctor-related operations.
    
    Supports:
    - GET: Retrieve list of all doctors
    - POST: Create a new doctor with surname, profession, and optional hospital_ID
    """
    
    # Expected number of fields for a doctor entity
    DOCTOR_FIELD_COUNT = 3
    
    def get(self):
        """
        Retrieve and display all doctors.
        
        Renders the doctor.html template with a list of all doctor records.
        """
        items = self.get_all_entities(KEY_PREFIX_DOCTOR, KEY_AUTO_ID_DOCTOR)
        
        if self.get_status() != 400:
            self.render('templates/doctor.html', items=items)

    def post(self):
        """
        Create a new doctor.
        
        Required fields:
        - surname: Doctor's surname
        - profession: Doctor's profession/specialty
        
        Optional fields:
        - hospital_ID: ID of the hospital where the doctor works
        
        If hospital_ID is provided, validates that the hospital exists.
        
        Returns:
            Success message with doctor ID, or error message on failure
        """
        surname = self.get_argument('surname')
        profession = self.get_argument('profession')
        hospital_ID = self.get_argument('hospital_ID')

        # Validate required fields
        if not surname or not profession:
            self.set_status(400)
            self.write("Surname and profession required")
            return

        logging.debug(f"Doctor creation: surname={surname}, profession={profession}")

        try:
            # Validate hospital_ID if provided
            if hospital_ID:
                hospital_key = f"{KEY_PREFIX_HOSPITAL}{hospital_ID}"
                if not self.check_entity_exists(hospital_key):
                    self.set_status(400)
                    self.write("No hospital with such ID")
                    return

            # Get next available ID
            entity_id = self.get_next_id(KEY_AUTO_ID_DOCTOR)
            entity_key = f"{KEY_PREFIX_DOCTOR}{entity_id}"
            
            # Prepare fields dictionary
            fields = {
                "surname": surname,
                "profession": profession,
                "hospital_ID": hospital_ID
            }
            
            # Create entity using batch operation
            success = self.create_entity(entity_key, fields, self.DOCTOR_FIELD_COUNT)
            
            if success:
                self.write(f'OK: ID {entity_id} for {surname}')
            else:
                self.set_status(500)
                self.write(ERROR_SOMETHING_WRONG)
                
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
        except ValueError as e:
            self._handle_value_error(e)


class PatientHandler(BaseRedisHandler):
    """
    Handler for patient-related operations.
    
    Supports:
    - GET: Retrieve list of all patients
    - POST: Create a new patient with surname, born_date, sex, and mpn
    """
    
    # Expected number of fields for a patient entity
    PATIENT_FIELD_COUNT = 4
    
    def get(self):
        """
        Retrieve and display all patients.
        
        Renders the patient.html template with a list of all patient records.
        """
        items = self.get_all_entities(KEY_PREFIX_PATIENT, KEY_AUTO_ID_PATIENT)
        
        if self.get_status() != 400:
            self.render('templates/patient.html', items=items)

    def post(self):
        """
        Create a new patient.
        
        Required fields:
        - surname: Patient's surname
        - born_date: Patient's date of birth
        - sex: Patient's sex (must be 'M' or 'F')
        - mpn: Medical policy number
        
        Validates that sex is one of the allowed values.
        
        Returns:
            Success message with patient ID, or error message on failure
        """
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        # Validate all required fields are provided
        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # Validate sex value (must be 'M' or 'F')
        if sex not in VALID_SEX_VALUES:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(f"Patient creation: surname={surname}, born_date={born_date}, sex={sex}, mpn={mpn}")

        try:
            # Get next available ID
            entity_id = self.get_next_id(KEY_AUTO_ID_PATIENT)
            entity_key = f"{KEY_PREFIX_PATIENT}{entity_id}"
            
            # Prepare fields dictionary
            fields = {
                "surname": surname,
                "born_date": born_date,
                "sex": sex,
                "mpn": mpn
            }
            
            # Create entity using batch operation
            success = self.create_entity(entity_key, fields, self.PATIENT_FIELD_COUNT)
            
            if success:
                self.write(f'OK: ID {entity_id} for {surname}')
            else:
                self.set_status(500)
                self.write(ERROR_SOMETHING_WRONG)
                
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
        except ValueError as e:
            self._handle_value_error(e)


class DiagnosisHandler(BaseRedisHandler):
    """
    Handler for diagnosis-related operations.
    
    Supports:
    - GET: Retrieve list of all diagnoses
    - POST: Create a new diagnosis linked to a patient
    """
    
    # Expected number of fields for a diagnosis entity
    DIAGNOSIS_FIELD_COUNT = 3
    
    def get(self):
        """
        Retrieve and display all diagnoses.
        
        Renders the diagnosis.html template with a list of all diagnosis records.
        """
        items = self.get_all_entities(KEY_PREFIX_DIAGNOSIS, KEY_AUTO_ID_DIAGNOSIS)
        
        if self.get_status() != 400:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        """
        Create a new diagnosis for a patient.
        
        Required fields:
        - patient_ID: ID of the patient
        - type: Type/category of the diagnosis
        
        Optional fields:
        - information: Additional information about the diagnosis
        
        Validates that the patient exists before creating the diagnosis.
        
        Returns:
            Success message with diagnosis ID and patient surname, or error message on failure
        """
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        # Validate required fields
        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patient ID and diagnosis type required")
            return

        logging.debug(f"Diagnosis creation: patient_ID={patient_ID}, type={diagnosis_type}, information={information}")

        try:
            # Validate that patient exists
            patient_key = f"{KEY_PREFIX_PATIENT}{patient_ID}"
            patient = self.get_redis_connection().hgetall(patient_key)
            
            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            # Get next available ID
            entity_id = self.get_next_id(KEY_AUTO_ID_DIAGNOSIS)
            entity_key = f"{KEY_PREFIX_DIAGNOSIS}{entity_id}"
            
            # Prepare fields dictionary
            fields = {
                "patient_ID": patient_ID,
                "type": diagnosis_type,
                "information": information
            }
            
            # Create entity using batch operation
            success = self.create_entity(entity_key, fields, self.DIAGNOSIS_FIELD_COUNT)
            
            if success:
                # Extract patient surname for response message
                patient_surname = patient.get(b'surname', b'Unknown').decode()
                self.write(f'OK: ID {entity_id} for patient {patient_surname}')
            else:
                self.set_status(500)
                self.write(ERROR_SOMETHING_WRONG)
                
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
        except (ValueError, AttributeError) as e:
            self._handle_value_error(e)


class DoctorPatientHandler(BaseRedisHandler):
    """
    Handler for doctor-patient relationship operations.
    
    Supports:
    - GET: Retrieve all doctor-patient relationships
    - POST: Create a link between a doctor and a patient
    """
    
    def get(self):
        """
        Retrieve and display all doctor-patient relationships.
        
        Uses Redis Sets to store relationships (one set per doctor containing patient IDs).
        Renders the doctor-patient.html template with relationship data.
        """
        items = {}
        try:
            redis_conn = self.get_redis_connection()
            auto_id_bytes = redis_conn.get(KEY_AUTO_ID_DOCTOR)
            
            if not auto_id_bytes:
                self.render('templates/doctor-patient.html', items=items)
                return
            
            max_id = int(auto_id_bytes.decode())
            
            for i in range(max_id):
                relationship_key = f"{KEY_PREFIX_DOCTOR_PATIENT}{i}"
                result = redis_conn.smembers(relationship_key)
                if result:
                    items[i] = result
                    
        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)
        except (ValueError, AttributeError) as e:
            logging.error(f"Error retrieving doctor-patient relationships: {e}")
            self.set_status(500)
            self.write(ERROR_SOMETHING_WRONG)
        else:
            if self.get_status() != 400:
                self.render('templates/doctor-patient.html', items=items)

    def post(self):
        """
        Create a link between a doctor and a patient.
        
        Required fields:
        - doctor_ID: ID of the doctor
        - patient_ID: ID of the patient
        
        Validates that both doctor and patient exist before creating the relationship.
        Uses Redis Set to store the relationship (allows multiple patients per doctor).
        
        Returns:
            Success message with both IDs, or error message on failure
        """
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        # Validate required fields
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(f"Doctor-patient link: doctor_ID={doctor_ID}, patient_ID={patient_ID}")

        try:
            redis_conn = self.get_redis_connection()
            
            # Validate that both doctor and patient exist
            doctor_key = f"{KEY_PREFIX_DOCTOR}{doctor_ID}"
            patient_key = f"{KEY_PREFIX_PATIENT}{patient_ID}"
            
            doctor = redis_conn.hgetall(doctor_key)
            patient = redis_conn.hgetall(patient_key)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            # Add patient to doctor's set of patients
            relationship_key = f"{KEY_PREFIX_DOCTOR_PATIENT}{doctor_ID}"
            redis_conn.sadd(relationship_key, patient_ID)
            
            self.write(f"OK: doctor ID: {doctor_ID}, patient ID: {patient_ID}")

        except redis.exceptions.ConnectionError as e:
            self.handle_redis_error(e)


def init_db():
    """
    Initialize the Redis database with default values.
    
    Sets up auto-incrementing ID counters for all entity types if the database
    hasn't been initialized before. This function is idempotent - it won't
    overwrite existing data if called multiple times.
    
    Creates the following keys:
    - hospital:autoID: Counter for hospital IDs (starts at 1)
    - doctor:autoID: Counter for doctor IDs (starts at 1)
    - patient:autoID: Counter for patient IDs (starts at 1)
    - diagnosis:autoID: Counter for diagnosis IDs (starts at 1)
    - db_initiated: Flag indicating database has been initialized
    """
    try:
        db_initiated = r.get(KEY_DB_INITIATED)
        if not db_initiated:
            # Use pipeline for atomic initialization
            pipe = r.pipeline()
            pipe.set(KEY_AUTO_ID_HOSPITAL, 1)
            pipe.set(KEY_AUTO_ID_DOCTOR, 1)
            pipe.set(KEY_AUTO_ID_PATIENT, 1)
            pipe.set(KEY_AUTO_ID_DIAGNOSIS, 1)
            pipe.set(KEY_DB_INITIATED, 1)
            pipe.execute()
            logging.info("Database initialized successfully")
    except redis.exceptions.ConnectionError as e:
        logging.error(f"Failed to initialize database: {e}")
        raise


def make_app():
    """
    Create and configure the Tornado web application.
    
    Sets up all URL routes and application settings. The application runs in
    debug mode with auto-reload enabled for development.
    
    Returns:
        tornado.web.Application: Configured Tornado application instance
        
    Routes:
        - /: Main page
        - /static/*: Static file serving
        - /hospital: Hospital management
        - /doctor: Doctor management
        - /patient: Patient management
        - /diagnosis: Diagnosis management
        - /doctor-patient: Doctor-patient relationship management
    """
    return tornado.web.Application([
        (r"/", MainHandler),
        (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': 'static/'}),
        (r"/hospital", HospitalHandler),
        (r"/doctor", DoctorHandler),
        (r"/patient", PatientHandler),
        (r"/diagnosis", DiagnosisHandler),
        (r"/doctor-patient", DoctorPatientHandler)
    ], autoreload=True, debug=True, compiled_template_cache=False, serve_traceback=True)


if __name__ == "__main__":
    """
    Application entry point.
    
    Initializes the database, creates the application, starts the server,
    and begins the IOLoop to handle requests.
    """
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info(f"Listening on port {PORT}")
    tornado.ioloop.IOLoop.current().start()