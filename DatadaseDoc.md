This document explains the database design and implementation for the AssureX system, a warranty and claim management platform. The system is built using Flask with SQLAlchemy ORM and MySQL as the database engine.

The database is responsible for storing users, products, warranty policies, warranties, claims, uploaded documents, repair history, model evaluations, and reviewer actions.

Technologies Used

- Flask – Web framework
- Flask-SQLAlchemy – ORM layer
- MySQL – Relational database
- PyMySQL – MySQL driver for Python
- Werkzeug – Password hashing

Connection string format:

mysql+pymysql://<user>:<password>@<host>:<port>/<database>?charset=utf8mb4

Environment variables are used to keep credentials out of the source code: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME.


 Database Creation Flow

The file database.py handles everything in three steps:

1. create_database() – Connects to MySQL server without selecting a database and runs CREATE DATABASE IF NOT EXISTS assurex with utf8mb4 charset.
2. create_tables() – Uses db.create_all() inside an app context to create all tables defined by the models.
3. seed_default_policies() – Inserts three default warranty policies (Electronics, Home Appliances, Mobile Devices) if they do not already exist.

Running the file directly triggers:

python database.py

Tables and Their Purpose

 1. users
Stores all system users. Each user has a unique user_id, email, hashed password, and one of four roles: Customer, Service-center employee, Claim reviewer, or Administrator.

A user can own many products, submit many claims, and perform review actions.

2. products
Represents a physical product owned by a user. Stores product name, category, brand, model number, serial number, purchase date, price, retailer, and warranty duration.

Each product belongs to one user and can have multiple warranties and claims.

 3. warranty_policies
Acts as a template for warranties. It defines rules per product category, including coverage duration, covered faults, exclusions, required documents, repair and replacement conditions, hard-fail rules, warning rules, and manual-review rules stored as JSON.

Separating policies from warranties allows updating a policy without affecting existing warranties.

4. warranties
Represents an actual warranty applied to a product. It links a product to a policy and stores start date, expiry date, provider, coverage conditions, exclusions, service center info, and status (Active, Expired, Approaching Expiry).

5. claims
The core table. A claim is submitted by a user for a specific product and warranty. It stores fault details, damage type, purchase details, service history, previous replacement info, submission date, and status.

Status values form a lifecycle:

Draft -> Submitted -> Under Evaluation -> Additional Information Required / Manual Review -> Approved / Rejected -> Closed

 6. documents
Stores uploaded files linked to a claim and optionally a product. Each document records its type, original filename, stored path, extension, size, secure hash, OCR text, extracted fields, and whether it was verified by the user.

7. repair_history
Records repair events related to a claim: repair date, service center, whether it was authorized, description, replaced parts, cost, and the repair document reference.

8. evaluations
Stores the results of the claim evaluation process. It keeps predictions from two models: the Python model and the Teachable Machine model, along with their valid, invalid, and manual review confidences.

It also stores whether the two models matched, confidence difference, consistency status, warranty result, missing documents, contradictions, duplicate indicator, rule result, final decision, explanation, and reviewer comments.

 9. review_actions
Stores actions taken by reviewers on claims: Approve, Reject, Request Additional Information, or Override, along with comments and timestamps.

 Relationships Summary

- User -> Products : One-to-Many
- User -> Claims : One-to-Many
- User -> ReviewActions : One-to-Many
- Product -> Warranties : One-to-Many
- Product -> Claims : One-to-Many
- WarrantyPolicy -> Warranties : One-to-Many
- Warranty -> Claims : One-to-Many
- Claim -> Documents : One-to-Many
- Claim -> RepairHistory : One-to-Many
- Claim -> Evaluations : One-to-Many
- Claim -> ReviewActions : One-to-Many

Cascade delete is applied to dependent records such as documents, repairs, evaluations, and review actions when a claim is deleted.


Design Decisions

1. JSON columns are used for flexible rule sets such as hard-fail rules, warning rules, and exclusions because they change frequently and vary per policy.
2. Policy and Warranty are separated to make the system configurable without breaking historical data.
3. Dual-model evaluation using Python and Teachable Machine increases reliability by comparing two independent predictions.
4. Enum types are used for controlled fields such as role, claim status, warranty status, and decision results to keep data consistent.
5. Indexes are added on frequently queried fields such as user_id, serial_number, claim_id, and status.


How to Run

1. Install dependencies:

pip install flask flask-sqlalchemy pymysql

2. Set environment variables or rely on defaults:

export DB_USER=root
export DB_PASSWORD=yourpassword
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=assurex

3. Run the setup script:

python database.py

The script will create the database if it does not exist, create all tables, and insert the three default warranty policies.

---

 Notes and Possible Improvements

- datetime.utcnow is deprecated in newer Python versions; datetime.now(timezoneutc)is recommended.
- Add CheckConstraint to prevent negative prices.
- Add composite unique constraints such as user and serial number where needed.
- Consider using Flask-Migrate instead of db.create_all() for production schema changes.
- Soft delete could be added to preserve historical records instead of permanent deletion.
- Storing file hashes and OCR text should follow data-protection rules if personal data is involved.

Conclusion

The AssureX database is built around a clear separation between users, products, warranties, and claims. The design supports flexible warranty policies, dual-model claim evaluation, and full tracking of documents and reviewer decisions. With the setup script in database.py, the entire schema and default policies can be created in a single command, making the system easy to initialize and extend.