# ASSUREX CLAIM ENGINE
## Technical System Architecture, Policy Engine & Verification Report

**Project Title:** AssureX Claim Engine
**Category:** NextWave AI & ML | AI-Powered Document Ops
**Core Technologies:** Flask (Python Framework), MySQL Database Server, HTML5/CSS3/JavaScript, Scikit-Learn, Google Teachable Machine Engine

---

### 1. SYSTEM OVERVIEW & ARCHITECTURAL FOUNDATIONS

#### 1.1 Problem Statement & Industrial Context
In standard manufacturing and retail warranty operations, processing claim requests requires significant manual evaluation. Human adjusters are tasked with inspecting purchase receipts, analyzing warranty coverage durations, cross-referencing past service logs, and verifying damage evidence. This conventional workflow suffers from systematic inefficiencies:
* Prolonged claim processing cycles leading to operational delays.
* Susceptibility to oversight, fraud, and misinterpretation of policy exclusions.
* Inconsistent adjudication decisions across different claim handlers.

#### 1.2 Proposed Solution
AssureX Claim Engine introduces an automated dual-AI claim verification and triage framework. The system extracts and structures submitted claim data, evaluates compliance against deterministic business policy rules, and submits each claim through two parallel Machine Learning models:
1. **Tabular Machine Learning Model (Python):** Analyzes numerical and categorical claim features such as product age, remaining warranty period, and historical repair counts.
2. **Visual Image Classification Model (Google Teachable Machine):** Processes standardized **Claim Summary Cards** generated automatically from claim metadata.

The final adjudication state (**Valid Claim**, **Invalid Claim**, or **Manual Review**) is determined by a unified engine that reconciles policy enforcement, model predictions, and confidence thresholds.

---

### 2. SYSTEM ARCHITECTURE & TECH STACK

* **Presentation Layer (Frontend):** Responsive user interface constructed using HTML5, CSS3, and JavaScript (Vanilla JS / Bootstrap framework).
* **Application Layer (Backend Framework):** Flask (Python framework) handling RESTful endpoints, database queries, authentication controls, and orchestration of the evaluation engine.
* **Persistence Layer (Relational Database):** MySQL Database Server (`assurex` schema) managing relational structures and historical audit logs.
* **Intelligence Layer (Machine Learning):** Python data science stack (`scikit-learn`, `pandas`, `numpy`, `pickle`) combined with a trained Google Teachable Machine image classification model.

---

### 3. DATABASE SCHEMA & DATA DICTIONARY

The application operates on the `assurex` relational database schema in MySQL. Below is the detailed specification of the core tables:

#### 3.1 Data Dictionary Specifications

##### 1. Table: `users`
* `user_id` (INT, Primary Key, Auto Increment): System identifier for registered user accounts.
* `full_name` (VARCHAR): Legal full name of the user.
* `email` (VARCHAR, Unique Constraint): Primary email credential.
* `password_hash` (VARCHAR): Hashed string for account authentication.
* `role` (ENUM): Access role assigned to the user (`Customer`, `Reviewer`, `Admin`).
* `created_at` (TIMESTAMP): Date and time of account creation.

##### 2. Table: `products`
* `product_id` (INT, Primary Key, Auto Increment): Identifier for physical products registered in the database.
* `user_id` (INT, Foreign Key -> `users.user_id`): Account owner associated with the product.
* `product_name` (VARCHAR): Model title.
* `category` (VARCHAR): Product classification (e.g., Smartphone, Laptop, Television).
* `brand` (VARCHAR): Equipment manufacturer.
* `model_number` (VARCHAR): Manufacturer model designation.
* `serial_number` (VARCHAR, Unique Constraint): Unique physical hardware serial number.
* `purchase_date` (DATE): Invoice purchase date.
* `purchase_price` (DECIMAL): Purchase cost.

##### 3. Table: `warranties`
* `warranty_id` (INT, Primary Key, Auto Increment): Coverage record identifier.
* `product_id` (INT, Foreign Key -> `products.product_id`): Linked product record.
* `policy_id` (INT, Foreign Key -> `warranty_policies.policy_id`): Associated warranty policy configuration.
* `start_date` (DATE): Inception date of active coverage.
* `expiry_date` (DATE): Expiration date of coverage.
* `warranty_type` (ENUM): Coverage level (`Standard`, `Extended`).
* `status` (ENUM): Operational state (`Active`, `Expired`, `Pending_Expiry`).

##### 4. Table: `claims`
* `claim_id` (INT, Primary Key, Auto Increment): Identifier assigned to submitted warranty claims.
* `user_id` (INT, Foreign Key -> `users.user_id`): Account submitting the claim.
* `product_id` (INT, Foreign Key -> `products.product_id`): Hardware item under review.
* `warranty_id` (INT, Foreign Key -> `warranties.warranty_id`): Coverage record applied.
* `fault_date` (DATE): Date the reported hardware fault occurred.
* `fault_description` (TEXT): Statement describing product malfunction.
* `claim_status` (ENUM): Lifecycle state (`Draft`, `Submitted`, `Under_Evaluation`, `Approved`, `Rejected`, `Manual_Review`).
* `submission_date` (TIMESTAMP): Submission timestamp.

##### 5. Table: `documents`
* `document_id` (INT, Primary Key, Auto Increment): File attachment identifier.
* `claim_id` (INT, Foreign Key -> `claims.claim_id`): Linked claim record.
* `file_name` (VARCHAR): System filename stored on disk.
* `file_type` (VARCHAR): Extension type (`pdf`, `jpg`, `png`).
* `file_hash` (VARCHAR): SHA-256 hash string generated for attachment duplicate detection.
* `uploaded_at` (TIMESTAMP): File upload timestamp.

##### 6. Table: `evaluations`
* `evaluation_id` (INT, Primary Key, Auto Increment): Evaluation audit entry identifier.
* `claim_id` (INT, Foreign Key -> `claims.claim_id`): Evaluated claim.
* `python_predicted_class` (VARCHAR): Prediction output from Python model (`Valid`, `Invalid`, `Manual_Review`).
* `python_confidence` (FLOAT): Confidence probability value from Python model.
* `tm_predicted_class` (VARCHAR): Prediction output from Teachable Machine image classifier
* `tm_confidence` (FLOAT): Confidence probability value from Teachable Machine
* `confidence_difference` (FLOAT): Absolute variance between model confidence outputs (`|Python_Conf - TM_Conf|`)
* `model_match_status` (VARCHAR): Reconciliation outcome (`Strong Match`, `Disagreement`, `Low Confidence`)
* `rule_validation_result` (VARCHAR): Compliance result from business rule execution (`Pass`, `Fail`, `Warnings`)
* `final_decision` (VARCHAR): System adjudication state (`Valid Claim`, `Invalid Claim`, `Manual Review`)

##### 7. Table: `repair_history`
* `repair_id` (INT, Primary Key, Auto Increment): Historical repair log entry
* `product_id` (INT, Foreign Key -> `products.product_id`): Serviced product item
* `repair_date` (DATE): Date of historical service
* `service_center` (VARCHAR): Facility name where repair was performed
* `is_authorized` (BOOLEAN): Boolean status tracking authorization of repair facility
* `replaced_parts` (TEXT): Summary of altered components
* `repair_cost` (DECIMAL): Expenditure incurred during repair

##### 8. Table: `review_actions`
* `action_id` (INT, Primary Key, Auto Increment): Audit record for manual reviewer adjustments
* `claim_id` (INT, Foreign Key -> `claims.claim_id`): Evaluated claim item
* `reviewer_id` (INT, Foreign Key -> `users.user_id`): Reviewer account making the entry
* `previous_decision` (VARCHAR): Automated recommendation generated by AI engine
* `final_action` (ENUM): Official disposition assigned (`Approved`, `Rejected`, `Requested_Info`)
* `reviewer_comments` (TEXT): Justification statement provided by reviewer
* `action_timestamp` (TIMESTAMP): Audit record creation time

##### 9. Table: `warranty_policies`
* `policy_id` (INT, Primary Key, Auto Increment): Policy configuration entry identifier.
* `category_name` (VARCHAR): Target product category
* `coverage_months` (INT): Baseline warranty window duration in months
* `max_claim_limit` (DECIMAL): Maximum financial coverage limit.
* `allow_unauthorized_repair` (BOOLEAN): Policy flag regarding third-party repairs

---

### 4. MACHINE LEARNING PIPELINE & DUAL-AI ARCHITECTURE

The **AssureX Claim Engine** implements a dual-channel analysis pipeline:

#### 4.1 Tabular Classification Pipeline (Python Scikit-Learn)
To determine the optimal classification algorithm for processing tabular claim features (such as product age, remaining active coverage days, past repair frequency, and claimed financial values), three models were benchmarked:
1. **Logistic Regression:** Linear model initialized via `LogisticRegression(max_iter=3000)`
2. **Decision Tree Classifier:** Non-linear single tree model initialized via `DecisionTreeClassifier()`
3. **Random Forest Classifier:** Ensemble architecture initialized via `RandomForestClassifier(n_estimators=300)`

##### Model Training Protocol
The model training and validation workflow proceeded through five distinct steps:
* **Model Training:** Models were trained on the training dataset and evaluated on validation data
* **Selection Metric:** The optimal algorithm was chosen dynamically based on the highest **F1 Macro** metric achieved on validation data:
  ```python
  best_name = max(validation_results, key=lambda key: validation_results[key]["f1_macro"])