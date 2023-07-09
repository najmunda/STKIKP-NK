DROP TABLE IF EXISTS cases;
DROP TABLE IF EXISTS symptoms;
DROP TABLE IF EXISTS symptom_codes;
DROP TABLE IF EXISTS users;

CREATE TABLE cases (
  case_id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  icd_code TEXT NOT NULL
);

CREATE TABLE symptoms (
  symptom_id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  negativity INTEGER NOT NULL,
  symptom_code TEXT NOT NULL,
  FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
);

CREATE TABLE symptom_codes (
  symptom_code_id INTEGER PRIMARY KEY AUTOINCREMENT,
  symptom TEXT NOT NULL,
  symptom_code TEXT UNIQUE NOT NULL,
  symptom_code_negate TEXT UNIQUE NOT NULL
);

CREATE TABLE users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  fullname TEXT NOT NULL,
  nickname TEXT NOT NULL
);