# Ревью кода Python 3 для рефакторинга
_Exported on 14/12/2025 at 18:24:51 GMT+3 from Cursor (2.2.20)_

---

**User**

@python3-app/  Выступи в роли Senior-разработчика. Проведи ревью кода с целью рефакторинга.

Задачи (Logical):
1. Найди участки кода, которые сложны для понимания, имеют "code smells" или неоптимизированы.
2. Предложи улучшенные версии этих участков кода.
3. Добавь комментарии (Docstrings), объясняющие сложные моменты.

Важно (Explicit): Функциональность приложения должна сохраниться полностью. Не меняй внешние интерфейсы API.

---

**Cursor**


Изучаю основные файлы проекта для анализа кода и выявления участков для рефакторинга.



Анализирую код и выявляю участки для рефакторинга. Составляю план улучшений.



Выявлены проблемы:
1. Дублирование кода в обработчиках
2. Глобальная переменная Redis
3. Магические числа (4, 3)
4. Конкатенация строк вместо f-strings
5. Ручной подсчёт полей через `a += r.hset(...)`
6. Отсутствие docstrings
7. Неэффективный перебор всех ID
8. Несогласованная обработка ошибок

Приступаю к рефакторингу с сохранением функциональности.



Рефакторинг кода с сохранением функциональности:


```python
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


class MainHandler(tornado.web.RequestHandler):
    """
    Handler for the main page.
    
    Renders the index.html template.
    """
    
    def get(self):
        """Render the main index page."""
        self.render('templates/index.html')


class HospitalHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("hospital:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("hospital:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/hospital.html', items=items)

    def post(self):
        name = self.get_argument('name')
        address = self.get_argument('address')
        beds_number = self.get_argument('beds_number')
        phone = self.get_argument('phone')

        if not name or not address:
            self.set_status(400)
            self.write("Hospital name and address required")
            return

        logging.debug(name + ' ' + address + ' ' + beds_number + ' ' + phone)

        try:
            ID = r.get("hospital:autoID").decode()

            a  = r.hset("hospital:" + ID, "name", name)
            a += r.hset("hospital:" + ID, "address", address)
            a += r.hset("hospital:" + ID, "phone", phone)
            a += r.hset("hospital:" + ID, "beds_number", beds_number)

            r.incr("hospital:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + name)


class DoctorHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("doctor:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        profession = self.get_argument('profession')
        hospital_ID = self.get_argument('hospital_ID')

        if not surname or not profession:
            self.set_status(400)
            self.write("Surname and profession required")
            return

        logging.debug(surname + ' ' + profession)

        try:
            ID = r.get("doctor:autoID").decode()

            if hospital_ID:
                # check that hospital exist
                hospital = r.hgetall("hospital:" + hospital_ID)

                if not hospital:
                    self.set_status(400)
                    self.write("No hospital with such ID")
                    return

            a  = r.hset("doctor:" + ID, "surname", surname)
            a += r.hset("doctor:" + ID, "profession", profession)
            a += r.hset("doctor:" + ID, "hospital_ID", hospital_ID)

            r.incr("doctor:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class PatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("patient:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("patient:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/patient.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # wow what a check
        if sex not in ['M', 'F']:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(surname + ' ' + born_date + ' ' + sex + ' ' + mpn)

        try:
            ID = r.get("patient:autoID").decode()

            a  = r.hset("patient:" + ID, "surname", surname)
            a += r.hset("patient:" + ID, "born_date", born_date)
            a += r.hset("patient:" + ID, "sex", sex)
            a += r.hset("patient:" + ID, "mpn", mpn)

            r.incr("patient:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```


Рефакторинг обработчиков, начиная с HospitalHandler:


```python
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
                
        except (redis.exceptions.ConnectionError, ValueError) as e:
            self.handle_redis_error(e) if isinstance(e, redis.exceptions.ConnectionError) else self._handle_value_error(e)


class DoctorHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("doctor:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        profession = self.get_argument('profession')
        hospital_ID = self.get_argument('hospital_ID')

        if not surname or not profession:
            self.set_status(400)
            self.write("Surname and profession required")
            return

        logging.debug(surname + ' ' + profession)

        try:
            ID = r.get("doctor:autoID").decode()

            if hospital_ID:
                # check that hospital exist
                hospital = r.hgetall("hospital:" + hospital_ID)

                if not hospital:
                    self.set_status(400)
                    self.write("No hospital with such ID")
                    return

            a  = r.hset("doctor:" + ID, "surname", surname)
            a += r.hset("doctor:" + ID, "profession", profession)
            a += r.hset("doctor:" + ID, "hospital_ID", hospital_ID)

            r.incr("doctor:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class PatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("patient:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("patient:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/patient.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # wow what a check
        if sex not in ['M', 'F']:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(surname + ' ' + born_date + ' ' + sex + ' ' + mpn)

        try:
            ID = r.get("patient:autoID").decode()

            a  = r.hset("patient:" + ID, "surname", surname)
            a += r.hset("patient:" + ID, "born_date", born_date)
            a += r.hset("patient:" + ID, "sex", sex)
            a += r.hset("patient:" + ID, "mpn", mpn)

            r.incr("patient:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```


Добавляю метод обработки ошибок и продолжаю рефакторинг остальных обработчиков:


```python
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
                
        except (redis.exceptions.ConnectionError, ValueError) as e:
            self.handle_redis_error(e) if isinstance(e, redis.exceptions.ConnectionError) else self._handle_value_error(e)


class DoctorHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("doctor:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        profession = self.get_argument('profession')
        hospital_ID = self.get_argument('hospital_ID')

        if not surname or not profession:
            self.set_status(400)
            self.write("Surname and profession required")
            return

        logging.debug(surname + ' ' + profession)

        try:
            ID = r.get("doctor:autoID").decode()

            if hospital_ID:
                # check that hospital exist
                hospital = r.hgetall("hospital:" + hospital_ID)

                if not hospital:
                    self.set_status(400)
                    self.write("No hospital with such ID")
                    return

            a  = r.hset("doctor:" + ID, "surname", surname)
            a += r.hset("doctor:" + ID, "profession", profession)
            a += r.hset("doctor:" + ID, "hospital_ID", hospital_ID)

            r.incr("doctor:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class PatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("patient:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("patient:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/patient.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # wow what a check
        if sex not in ['M', 'F']:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(surname + ' ' + born_date + ' ' + sex + ' ' + mpn)

        try:
            ID = r.get("patient:autoID").decode()

            a  = r.hset("patient:" + ID, "surname", surname)
            a += r.hset("patient:" + ID, "born_date", born_date)
            a += r.hset("patient:" + ID, "sex", sex)
            a += r.hset("patient:" + ID, "mpn", mpn)

            r.incr("patient:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```

```python
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


class DoctorHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("doctor:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        profession = self.get_argument('profession')
        hospital_ID = self.get_argument('hospital_ID')

        if not surname or not profession:
            self.set_status(400)
            self.write("Surname and profession required")
            return

        logging.debug(surname + ' ' + profession)

        try:
            ID = r.get("doctor:autoID").decode()

            if hospital_ID:
                # check that hospital exist
                hospital = r.hgetall("hospital:" + hospital_ID)

                if not hospital:
                    self.set_status(400)
                    self.write("No hospital with such ID")
                    return

            a  = r.hset("doctor:" + ID, "surname", surname)
            a += r.hset("doctor:" + ID, "profession", profession)
            a += r.hset("doctor:" + ID, "hospital_ID", hospital_ID)

            r.incr("doctor:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class PatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("patient:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("patient:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/patient.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # wow what a check
        if sex not in ['M', 'F']:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(surname + ' ' + born_date + ' ' + sex + ' ' + mpn)

        try:
            ID = r.get("patient:autoID").decode()

            a  = r.hset("patient:" + ID, "surname", surname)
            a += r.hset("patient:" + ID, "born_date", born_date)
            a += r.hset("patient:" + ID, "sex", sex)
            a += r.hset("patient:" + ID, "mpn", mpn)

            r.incr("patient:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```

```python
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


class PatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("patient:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("patient:" + str(i))
                if result:
                    items.append(result)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/patient.html', items=items)

    def post(self):
        surname = self.get_argument('surname')
        born_date = self.get_argument('born_date')
        sex = self.get_argument('sex')
        mpn = self.get_argument('mpn')

        if not surname or not born_date or not sex or not mpn:
            self.set_status(400)
            self.write("All fields required")
            return

        # wow what a check
        if sex not in ['M', 'F']:
            self.set_status(400)
            self.write("Sex must be 'M' or 'F'")
            return

        logging.debug(surname + ' ' + born_date + ' ' + sex + ' ' + mpn)

        try:
            ID = r.get("patient:autoID").decode()

            a  = r.hset("patient:" + ID, "surname", surname)
            a += r.hset("patient:" + ID, "born_date", born_date)
            a += r.hset("patient:" + ID, "sex", sex)
            a += r.hset("patient:" + ID, "mpn", mpn)

            r.incr("patient:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 4):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for " + surname)


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```


Рефакторинг PatientHandler:


```python
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


class DiagnosisHandler(tornado.web.RequestHandler):
    def get(self):
        items = []
        try:
            ID = r.get("diagnosis:autoID").decode()

            for i in range(int(ID)):
                result = r.hgetall("diagnosis:" + str(i))
                if result:
                    items.append(result)
            
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/diagnosis.html', items=items)

    def post(self):
        patient_ID = self.get_argument('patient_ID')
        diagnosis_type = self.get_argument('type')
        information = self.get_argument('information')

        if not patient_ID or not diagnosis_type:
            self.set_status(400)
            self.write("Patiend ID and diagnosis type required")
            return

        logging.debug(patient_ID + ' ' + diagnosis_type + ' ' + information)

        try:
            ID = r.get("diagnosis:autoID").decode()

            patient = r.hgetall("patient:" + patient_ID)

            if not patient:
                self.set_status(400)
                self.write("No patient with such ID")
                return

            a  = r.hset("diagnosis:" + ID, "patient_ID", patient_ID)
            a += r.hset("diagnosis:" + ID, "type", diagnosis_type)
            a += r.hset("diagnosis:" + ID, "information", information)

            r.incr("diagnosis:autoID")
        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            if (a != 3):
                self.set_status(500)
                self.write("Something went terribly wrong")
            else:
                self.write('OK: ID ' + ID + " for patient " + patient[b'surname'].decode())


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```

```python
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


class DoctorPatientHandler(tornado.web.RequestHandler):
    def get(self):
        items = {}
        try:
            ID = r.get("doctor:autoID").decode()

            for i in range(int(ID)):
                result = r.smembers("doctor-patient:" + str(i))
                if result:
                    items[i] = result

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.render('templates/doctor-patient.html', items=items)

    def post(self):
        doctor_ID = self.get_argument('doctor_ID')
        patient_ID = self.get_argument('patient_ID')
        
        if not doctor_ID or not patient_ID:
            self.set_status(400)
            self.write("ID required")
            return

        logging.debug(doctor_ID + ' ' + patient_ID)

        try:
            patient = r.hgetall("patient:" + patient_ID)
            doctor = r.hgetall("doctor:" + doctor_ID)

            if not patient or not doctor:
                self.set_status(400)
                self.write("No such ID for doctor or patient")
                return

            r.sadd("doctor-patient:" + doctor_ID, patient_ID)

        except redis.exceptions.ConnectionError:
            self.set_status(400)
            self.write("Redis connection refused")
        else:
            self.write("OK: doctor ID: " + doctor_ID + ", patient ID: " + patient_ID)


def init_db():
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```

```python
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
    db_initiated = r.get("db_initiated")
    if not db_initiated:
        r.set("hospital:autoID", 1)
        r.set("doctor:autoID", 1)
        r.set("patient:autoID", 1)
        r.set("diagnosis:autoID", 1)
        r.set("db_initiated", 1)


def make_app():
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
    init_db()
    app = make_app()
    app.listen(PORT)
    tornado.options.parse_command_line()
    logging.info("Listening on " + str(PORT))
    tornado.ioloop.IOLoop.current().start()
```


Рефакторинг функций `init_db` и `make_app`:


```python
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
```


Проверяю ошибки линтера и читаю финальную версию файла:



Проверяю, что тесты проходят. Запускаю тесты:



Проверяю структуру проекта и наличие виртуального окружения:



Активирую виртуальное окружение и запускаю тесты:



Все 51 тест прошли. Рефакторинг завершён, функциональность сохранена.

## Резюме рефакторинга

### Выполненные улучшения:

1. Устранено дублирование кода
   - Создан базовый класс `BaseRedisHandler` с общими операциями
   - Все обработчики наследуются от базового класса
   - Общие паттерны вынесены в методы базового класса

2. Улучшена структура кода
   - Добавлены константы для магических чисел и строк
   - Использованы f-strings вместо конкатенации
   - Улучшена читаемость и поддерживаемость

3. Оптимизация работы с Redis
   - Использование pipeline для атомарных операций
   - Более эффективная обработка ошибок
   - Улучшенная валидация данных

4. Добавлена документация
   - Docstrings для всех классов и методов
   - Комментарии к сложным участкам
   - Описание параметров и возвращаемых значений

5. Улучшена обработка ошибок
   - Единообразная обработка ошибок Redis
   - Более информативные сообщения об ошибках
   - Логирование ошибок

6. Исправлены проблемы
   - Исправлена опечатка: "Patiend" → "Patient"
   - Убраны магические числа (4, 3) — заменены на константы
   - Улучшена валидация данных

### Основные изменения:

- Создан `BaseRedisHandler` с методами:
  - `get_all_entities()` — получение всех сущностей
  - `get_next_id()` — получение следующего ID
  - `create_entity()` — создание сущности через pipeline
  - `check_entity_exists()` — проверка существования
  - `handle_redis_error()` — обработка ошибок Redis

- Все обработчики рефакторены:
  - `HospitalHandler`
  - `DoctorHandler`
  - `PatientHandler`
  - `DiagnosisHandler`
  - `DoctorPatientHandler`

- Улучшены функции:
  - `init_db()` — использует pipeline для атомарной инициализации
  - `make_app()` — добавлена документация

### Результаты:

- Все 51 тест проходят успешно
- Функциональность полностью сохранена
- API интерфейсы не изменены
- Код стал более читаемым и поддерживаемым
- Добавлена полная документация

Код готов к использованию и соответствует лучшим практикам разработки.

---

**User**

добавь в файл @README.md  в загаловок # 4. 
что было проделано

---

**Cursor**


Добавляю раздел о рефакторинге в README.md.



Добавляю раздел о рефакторинге в README.md.


```markdown
# 1. Добавляем тесты

В проект были добавлены комплексные юнит-тесты для проверки функциональности приложения управления больницей.

## Что было сделано

### Тестовое покрытие

Создан файл `python3-app/test_main.py` с **51 тестом**, покрывающим:

- **Все API эндпоинты**: GET и POST запросы для всех handlers
  - MainHandler (главная страница)
  - HospitalHandler (управление больницами)
  - DoctorHandler (управление врачами)
  - PatientHandler (управление пациентами)
  - DiagnosisHandler (управление диагнозами)
  - DoctorPatientHandler (связь врачей и пациентов)

- **Бизнес-логика и валидация**:
  - Проверка обязательных полей
  - Валидация значений (например, sex должен быть 'M' или 'F')
  - Проверка существования связанных сущностей
  - Обработка ошибок подключения к Redis

- **Граничные случаи (edge cases)**:
  - Пустые значения полей
  - Отсутствующие аргументы
  - Невалидные ID связанных сущностей
  - Инкремент autoID
  - Пропуски в ID при получении данных

- **Инициализация базы данных**:
  - Создание autoID ключей
  - Идемпотентность функции init_db

### Технологии

- **pytest** — фреймворк для тестирования
- **pytest-tornado** — плагин для тестирования Tornado приложений
- **fakeredis** — мокирование Redis (не требуется реальный Redis сервер)
- **unittest.mock** — для патчинга зависимостей

### Запуск тестов

```bash
cd python3-app

# С использованием uv
uv run pytest test_main.py -v

# Или через виртуальное окружение
.venv/bin/pytest test_main.py -v

# Запуск конкретного теста
pytest test_main.py::TestHospitalHandler::test_hospital_post_success -v
```

Все тесты изолированы и используют fake Redis, поэтому не требуют запущенного Redis сервера.

## Дополнительные улучшения

- Добавлена поддержка **uv** для управления зависимостями и версионирования проекта
- Создан `pyproject.toml` с конфигурацией проекта и зависимостями
- Добавлен `docker-compose.yml` для удобного запуска Redis
- Обновлена документация в `python3-app/README.md`


# 2. Добавляем стресстесты

В проект были добавлены стресстесты

[Как запустить стресстесты](stresstest_guide.md)


# 3. Пишем документацию
Обновил README.md, добавил документацию по API


# 4. Рефакторинг кода

Проведен комплексный рефакторинг кода с целью улучшения читаемости, поддерживаемости и устранения code smells, при полном сохранении функциональности приложения.

## Что было сделано

### Устранение дублирования кода

- **Создан базовый класс `BaseRedisHandler`**:
  - Инкапсулирует общие паттерны работы с Redis
  - Унифицирует обработку ошибок подключения
  - Предоставляет методы для работы с сущностями (получение, создание, валидация)
  - Все обработчики теперь наследуются от базового класса

- **Вынесены общие операции**:
  - `get_all_entities()` — получение всех сущностей типа
  - `get_next_id()` — получение следующего доступного ID
  - `create_entity()` — создание сущности через Redis pipeline
  - `check_entity_exists()` — проверка существования сущности
  - `handle_redis_error()` — единообразная обработка ошибок Redis

### Улучшение структуры кода

- **Добавлены константы** вместо магических чисел и строк:
  - Префиксы ключей Redis (`KEY_PREFIX_HOSPITAL`, `KEY_PREFIX_DOCTOR`, и т.д.)
  - Ключи autoID (`KEY_AUTO_ID_HOSPITAL`, и т.д.)
  - Валидные значения (`VALID_SEX_VALUES`)
  - Сообщения об ошибках (`ERROR_REDIS_CONNECTION`, `ERROR_SOMETHING_WRONG`)

- **Использование f-strings** вместо конкатенации строк:
  - Улучшена читаемость кода
  - Более эффективная работа со строками

- **Улучшена валидация данных**:
  - Единообразная проверка обязательных полей
  - Более информативные сообщения об ошибках

### Оптимизация работы с Redis

- **Использование Redis Pipeline**:
  - Атомарные batch-операции при создании сущностей
  - Более эффективное использование сетевых ресурсов
  - Гарантия целостности данных

- **Улучшенная обработка ошибок**:
  - Централизованная обработка ошибок подключения
  - Логирование ошибок для отладки
  - Корректные HTTP статус-коды

### Документация кода

- **Добавлены docstrings** для всех классов и методов:
  - Описание назначения классов и методов
  - Документация параметров и возвращаемых значений
  - Примеры использования и примечания

- **Комментарии к сложным участкам**:
  - Объяснение логики работы с Redis
  - Примечания о производительности
  - Описание бизнес-логики

### Исправленные проблемы

- **Исправлена опечатка**: "Patiend" → "Patient" в сообщении об ошибке
- **Устранены магические числа**: заменены на именованные константы
- **Улучшена читаемость**: код стал более структурированным и понятным

### Результаты рефакторинга

✅ **Все 51 тест проходят успешно** — функциональность полностью сохранена  
✅ **API интерфейсы не изменены** — обратная совместимость обеспечена  
✅ **Код стал более читаемым** — улучшена поддерживаемость  
✅ **Устранены code smells** — код соответствует best practices  
✅ **Добавлена полная документация** — упрощено понимание кода

### Основные улучшения в коде

**До рефакторинга:**
```python
a  = r.hset("hospital:" + ID, "name", name)
a += r.hset("hospital:" + ID, "address", address)
a += r.hset("hospital:" + ID, "phone", phone)
a += r.hset("hospital:" + ID, "beds_number", beds_number)
if (a != 4):
    self.set_status(500)
    self.write("Something went terribly wrong")
```

**После рефакторинга:**
```python
fields = {
    "name": name,
    "address": address,
    "phone": phone,
    "beds_number": beds_number
}
success = self.create_entity(entity_key, fields, self.HOSPITAL_FIELD_COUNT)
```

Код стал более декларативным, читаемым и безопасным.
```


Добавлен раздел "# 4. Рефакторинг кода" в README.md с описанием выполненных улучшений:

- Устранение дублирования кода (базовый класс `BaseRedisHandler`)
- Улучшение структуры (константы, f-strings)
- Оптимизация работы с Redis (pipeline, обработка ошибок)
- Документация (docstrings, комментарии)
- Исправленные проблемы
- Результаты рефакторинга
- Примеры улучшений кода

Раздел структурирован и описывает все изменения, внесённые в ходе рефакторинга.

