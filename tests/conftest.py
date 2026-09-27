"""Shared pytest fixtures."""

import pytest
import pandas as pd


@pytest.fixture
def sample_schema():
    return {
        "customers": [
            "customer_id (int)",
            "name (varchar)",
            "email (varchar)",
            "city (varchar)",
            "registration_date (date)",
        ],
        "products": [
            "product_id (int)",
            "product_name (varchar)",
            "category (varchar)",
            "price (decimal)",
        ],
        "orders": [
            "order_id (int)",
            "customer_id (int)",
            "product_id (int)",
            "quantity (int)",
            "order_date (date)",
            "amount (decimal)",
        ],
    }


@pytest.fixture
def sample_relationships():
    return [
        "orders.customer_id -> customers.customer_id",
        "orders.product_id -> products.product_id",
    ]


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame(
        {
            "name": ["Rohit Verma", "Rahul Sharma", "Neha Singh"],
            "total_purchase": [137000, 70000, 60000],
        }
    )
