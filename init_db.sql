CREATE DATABASE loan_tracker;

USE loan_tracker;

CREATE TABLE people (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(255),
    notes TEXT
);

CREATE TABLE loans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_id INT NOT NULL,
    direction TINYINT NOT NULL,
    principal DECIMAL(10,2) NOT NULL,
    paid DECIMAL(10,2) DEFAULT 0,
    given_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    due_date DATE NOT NULL,
    notes TEXT,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  loan_id INT NOT NULL,
  paid_date DATE NOT NULL,
  amount DECIMAL(10,2) NOT NULL DEFAULT 0,
  note VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_payments_loan_date (loan_id, paid_date),
  CONSTRAINT fk_payments_loan
    FOREIGN KEY (loan_id) REFERENCES loans(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
