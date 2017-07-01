
C:\WORK\Savin\StartStopp\app>set DJANGO_SETTINGS_MODULE=webapp.settings 

C:\WORK\Savin\StartStopp\app>python manage.py sql doctor       
BEGIN;
CREATE TABLE "doctor_doctor" (
    "id" serial NOT NULL PRIMARY KEY,
    "user_id" integer NOT NULL UNIQUE REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
)
;
CREATE TABLE "doctor_patient" (
    "id" serial NOT NULL PRIMARY KEY,
    "first_name" varchar(200) NOT NULL,
    "last_name" varchar(200) NOT NULL,
    "year_of_birth" integer CHECK ("year_of_birth" >= 0) NOT NULL,
    "gender" varchar(1) NOT NULL,
    "doctor_id" integer NOT NULL REFERENCES "doctor_doctor" ("id") DEFERRABLE INITIALLY DEFERRED,
    "status" varchar(1) NOT NULL
)
;
CREATE TABLE "doctor_entry" (
    "id" serial NOT NULL PRIMARY KEY,
    "dt" timestamp with time zone NOT NULL,
    "patient_id" integer NOT NULL REFERENCES "doctor_patient" ("id") DEFERRABLE INITIALLY DEFERRED
)
;
CREATE TABLE "doctor_disease_entries" (
    "id" serial NOT NULL PRIMARY KEY,
    "disease_id" varchar(8) NOT NULL,
    "entry_id" integer NOT NULL REFERENCES "doctor_entry" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("disease_id", "entry_id")
)
;
CREATE TABLE "doctor_disease" (
    "code" varchar(8) NOT NULL PRIMARY KEY,
    "group" varchar(128) NOT NULL,
    "description" varchar(200) NOT NULL
)
;
ALTER TABLE "doctor_disease_entries" ADD CONSTRAINT "disease_id_refs_code_2438b4ca" FOREIGN KEY ("disease_id") REFERENCES "doctor_disease" ("code") DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE "doctor_question_entries" (
    "id" serial NOT NULL PRIMARY KEY,
    "question_id" varchar(8) NOT NULL,
    "entry_id" integer NOT NULL REFERENCES "doctor_entry" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("question_id", "entry_id")
)
;
CREATE TABLE "doctor_question" (
    "code" varchar(8) NOT NULL PRIMARY KEY,
    "description" varchar(200) NOT NULL
)
;
ALTER TABLE "doctor_question_entries" ADD CONSTRAINT "question_id_refs_code_6214fc54" FOREIGN KEY ("question_id") REFERENCES "doctor_question" ("code") DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE "doctor_criteria_entries" (
    "id" serial NOT NULL PRIMARY KEY,
    "criteria_id" varchar(8) NOT NULL,
    "entry_id" integer NOT NULL REFERENCES "doctor_entry" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("criteria_id", "entry_id")
)
;
CREATE TABLE "doctor_criteria" (
    "code" varchar(8) NOT NULL PRIMARY KEY,
    "if_clause" varchar(1000) NOT NULL,
    "description" varchar(1000) NOT NULL
)
;
ALTER TABLE "doctor_criteria_entries" ADD CONSTRAINT "criteria_id_refs_code_7b8128be" FOREIGN KEY ("criteria_id") REFERENCES "doctor_criteria" ("code") DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE "doctor_druggroup" (
    "name" varchar(40) NOT NULL PRIMARY KEY,
    "column" varchar(8) NOT NULL,
    "keywords" varchar(200) NOT NULL
)
;
CREATE TABLE "doctor_drug_groups" (
    "id" serial NOT NULL PRIMARY KEY,
    "drug_id" integer NOT NULL,
    "druggroup_id" varchar(40) NOT NULL REFERENCES "doctor_druggroup" ("name") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("drug_id", "druggroup_id")
)
;
CREATE TABLE "doctor_drug" (
    "code" integer CHECK ("code" >= 0) NOT NULL PRIMARY KEY,
    "name" varchar(250) NOT NULL,
    "unit" varchar(64) NOT NULL,
    "doseperunit" double precision NOT NULL,
    "atc" varchar(8) NOT NULL,
    "substances" varchar(250) NOT NULL
)
;
ALTER TABLE "doctor_drug_groups" ADD CONSTRAINT "drug_id_refs_code_203d2ee3" FOREIGN KEY ("drug_id") REFERENCES "doctor_drug" ("code") DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE "doctor_drugentry" (
    "id" serial NOT NULL PRIMARY KEY,
    "entry_id" integer NOT NULL REFERENCES "doctor_entry" ("id") DEFERRABLE INITIALLY DEFERRED,
    "drug_id" integer NOT NULL REFERENCES "doctor_drug" ("code") DEFERRABLE INITIALLY DEFERRED,
    "dose_amount" double precision NOT NULL,
    "dose_time" varchar(1) NOT NULL
)
;
COMMIT;
