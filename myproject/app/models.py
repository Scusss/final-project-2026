import enum
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID, INET
from app.extensions import db

# External Supabase Auth table reference.
# This registers the table in SQLAlchemy metadata
# without making it a Flask application-managed table.

auth_users = db.Table(
    "users",
    db.metadata,
    db.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
    ),
    schema="auth",
)

class TransactionType(enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_PAYMENT = "loan_payment"
    ADJUSTMENT = "adjustment"


class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.SmallInteger, primary_key=True)
    role_name = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.Text)


class Customer(db.Model):
    __tablename__ = "customer"

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("auth.users.id", ondelete="RESTRICT"),
        primary_key=True
    )

    role_id = db.Column(
        db.SmallInteger,
        db.ForeignKey("roles.role_id"),
        nullable=False
    )

    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    account_status = db.Column(db.String(20), nullable=False, default="active")

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    role = db.relationship("Role")

    details = db.relationship(
        "CustomerDetails",
        back_populates="customer",
        uselist=False
    )


class CustomerDetails(db.Model):
    __tablename__ = "customer_details"

    detail_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id"),
        unique=True,
        nullable=False
    )

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))

    phone_number = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    address = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    customer = db.relationship(
        "Customer",
        back_populates="details"
    )


class Account(db.Model):
    __tablename__ = "accounts"

    account_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id"),
        nullable=False
    )

    account_number = db.Column(db.String(30), unique=True, nullable=False)
    account_type = db.Column(db.String(30), nullable=False)

    balance = db.Column(db.Numeric(19, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="PHP")

    status = db.Column(db.String(20), nullable=False, default="active")

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class TransactionList(db.Model):
    __tablename__ = "transaction_list"

    transaction_id = db.Column(db.BigInteger, primary_key=True)

    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.account_id"),
        nullable=False
    )

    reference_number = db.Column(db.String(60), unique=True, nullable=False)

    transaction_type = db.Column(
        db.String(30),
        nullable=False
    )

    amount = db.Column(db.Numeric(19, 2), nullable=False)

    balance_before = db.Column(db.Numeric(19, 2))
    balance_after = db.Column(db.Numeric(19, 2))

    description = db.Column(db.Text)

    status = db.Column(db.String(20), nullable=False, default="completed")

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class Beneficiary(db.Model):
    __tablename__ = "beneficiaries"

    beneficiary_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id"),
        nullable=False
    )

    beneficiary_name = db.Column(db.String(150), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(50))

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class Transfer(db.Model):
    __tablename__ = "transfers"

    transfer_id = db.Column(db.BigInteger, primary_key=True)

    sender_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.account_id"),
        nullable=False
    )

    recipient_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.account_id")
    )

    beneficiary_id = db.Column(
        db.BigInteger,
        db.ForeignKey("beneficiaries.beneficiary_id")
    )

    reference_number = db.Column(db.String(60), unique=True, nullable=False)

    amount = db.Column(db.Numeric(19, 2), nullable=False)
    description = db.Column(db.Text)

    transfer_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class Loan(db.Model):
    __tablename__ = "loans"

    loan_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id"),
        nullable=False
    )

    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.account_id")
    )

    loan_reference = db.Column(db.String(60), unique=True, nullable=False)
    loan_type = db.Column(db.String(50), nullable=False)

    principal_amount = db.Column(db.Numeric(19, 2), nullable=False)
    interest_rate = db.Column(db.Numeric(7, 4), nullable=False)

    loan_term_months = db.Column(db.Integer, nullable=False)
    monthly_payment = db.Column(db.Numeric(19, 2))

    outstanding_balance = db.Column(db.Numeric(19, 2), nullable=False)

    loan_status = db.Column(db.String(20), nullable=False, default="pending")

    application_date = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )
    approval_date = db.Column(db.DateTime(timezone=True))


class LoanPayment(db.Model):
    __tablename__ = "loan_payments"

    payment_id = db.Column(db.BigInteger, primary_key=True)

    loan_id = db.Column(
        db.BigInteger,
        db.ForeignKey("loans.loan_id"),
        nullable=False
    )

    transaction_id = db.Column(
        db.BigInteger,
        db.ForeignKey("transaction_list.transaction_id"),
        unique=True
    )

    payment_reference = db.Column(db.String(60), unique=True, nullable=False)

    payment_amount = db.Column(db.Numeric(19, 2), nullable=False)

    payment_date = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )

    payment_status = db.Column(db.String(20), nullable=False, default="completed")


class LoginHistory(db.Model):
    __tablename__ = "login_history"

    login_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id", ondelete="SET NULL"),
        nullable=True
    )

    username_attempted = db.Column(db.String(50))
    ip_address = db.Column(INET)
    device_info = db.Column(db.Text)

    login_status = db.Column(db.String(20), nullable=False)

    login_time = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class Notification(db.Model):
    __tablename__ = "notifications"

    notification_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id"),
        nullable=False
    )

    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(30))

    is_read = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    log_id = db.Column(db.BigInteger, primary_key=True)

    customer_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("customer.customer_id", ondelete="SET NULL")
    )

    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.BigInteger)

    description = db.Column(db.Text)
    ip_address = db.Column(INET)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now()
    )
