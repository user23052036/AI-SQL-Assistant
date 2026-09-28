-- AI Sales Database — SQLite version of database.sql (same schema and data).
-- Used when DB_BACKEND=sqlite, e.g. for the hosted demo. The app builds the
-- SQLite file from this script automatically; no manual setup is needed.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150),
    city VARCHAR(100),
    registration_date DATE
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    order_date DATE,
    amount DECIMAL(10,2),

    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE SET NULL,

    FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE SET NULL
);

INSERT INTO customers (name, email, city, registration_date)
VALUES
    ('Rahul Sharma',    'rahul@gmail.com',  'Mumbai',    '2025-01-10'),
    ('Priya Patil',     'priya@gmail.com',  'Pune',      '2025-02-15'),
    ('Amit Kumar',      'amit@gmail.com',   'Delhi',     '2025-03-20'),
    ('Sneha Joshi',     'sneha@gmail.com',  'Nagpur',    '2025-04-12'),
    ('Rohit Verma',     'rohit@gmail.com',  'Bangalore', '2025-05-18'),
    ('Neha Singh',      'neha@gmail.com',   'Hyderabad', '2025-06-22'),
    ('Vikas More',      'vikas@gmail.com',  'Nashik',    '2025-07-05'),
    ('Pooja Deshmukh',  'pooja@gmail.com',  'Amravati',  '2025-07-18');

INSERT INTO products (product_name, category, price)
VALUES
    ('Laptop',       'Electronics',  65000.00),
    ('Mobile Phone', 'Electronics',  30000.00),
    ('Keyboard',     'Accessories',   2500.00),
    ('Mouse',        'Accessories',   1200.00),
    ('Monitor',      'Electronics',  18000.00),
    ('Headphones',   'Accessories',   3500.00),
    ('Tablet',       'Electronics',  25000.00),
    ('Webcam',       'Accessories',   4500.00);

INSERT INTO orders (customer_id, product_id, quantity, order_date, amount)
VALUES
    (1, 1, 1, '2025-08-01', 65000.00),
    (1, 3, 2, '2025-08-05',  5000.00),
    (2, 2, 1, '2025-08-07', 30000.00),
    (2, 6, 1, '2025-08-12',  3500.00),
    (3, 5, 2, '2025-08-15', 36000.00),
    (3, 4, 2, '2025-08-17',  2400.00),
    (4, 7, 1, '2025-08-20', 25000.00),
    (4, 8, 1, '2025-08-22',  4500.00),
    (5, 1, 2, '2025-08-25', 130000.00),
    (5, 6, 2, '2025-08-27',  7000.00),
    (6, 2, 2, '2025-08-28', 60000.00),
    (7, 5, 1, '2025-08-29', 18000.00),
    (7, 3, 3, '2025-08-30',  7500.00),
    (8, 7, 2, '2025-08-31', 50000.00);
