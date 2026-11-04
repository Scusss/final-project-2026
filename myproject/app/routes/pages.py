
from functools import wraps
from uuid import UUID

from flask import (
    Blueprint,
    render_template,
    abort,
    redirect,
    url_for,
    flash,
    session,
    request,
)

from app.extensions import db, get_supabase_client
from app.models import (
    Account,
    Customer,
    CustomerDetails,
    TransactionList,
    Notification,
    Beneficiary,
)


pages = Blueprint("pages", __name__)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):

        customer_id = session.get("customer_id")
        access_token = session.get("access_token")

        if not customer_id or not access_token:
            session.clear()
            flash("Please log in to continue.")
            return redirect(url_for("auth.login"))

        try:
            customer_uuid = UUID(str(customer_id))

            # Verify the Supabase access token
            supabase = get_supabase_client()

            response = supabase.auth.get_user(access_token)

            if not response.user:
                raise ValueError("Invalid session")

            authenticated_id = UUID(str(response.user.id))

            if authenticated_id != customer_uuid:
                raise ValueError("User identity mismatch")

            # Verify customer still exists and is active
            customer = db.session.get(Customer, customer_uuid)

            if (
                customer is None
                or customer.is_locked
                or customer.account_status != "active"
            ):
                session.clear()
                flash("Your account is unavailable.")
                return redirect(url_for("auth.login"))

        except Exception:
            session.clear()
            flash("Your session has expired. Please log in again.")
            return redirect(url_for("auth.login"))

        return view(*args, **kwargs)

    return wrapped_view


def get_current_customer():

    customer_id = session.get("customer_id")

    try:
        customer_uuid = UUID(str(customer_id))
    except (ValueError, TypeError, AttributeError):
        session.clear()
        abort(401)

    customer = db.session.get(Customer, customer_uuid)

    if customer is None:
        session.clear()
        abort(401)

    return customer


def get_customer_account(customer):

    return (
        Account.query
        .filter_by(customer_id=customer.customer_id)
        .order_by(Account.account_id.asc())
        .first()
    )


def get_customer_details(customer):

    return CustomerDetails.query.filter_by(
        customer_id=customer.customer_id
    ).first()


@pages.route("/")
@login_required
def home():
    customer = get_current_customer()
    account = get_customer_account(customer)
    details = get_customer_details(customer)

    balance = account.balance if account else 0
    account_type = (
        account.account_type or "savings"
    ) if account else "savings"

    account_type_label = account_type.replace("_", " ").title()

    # Count unread notifications for this customer.
    unread_count = Notification.query.filter_by(
        customer_id=customer.customer_id,
        is_read=False,
    ).count()

    return render_template(
        "home.html",
        balance=balance,
        username=customer.username,
        first_name=details.first_name if details else "",
        last_name=details.last_name if details else "",
        account_type=account_type_label,
        unread_count=unread_count,
        role_name=(customer.role.role_name if customer.role else "customer"),
    )


@pages.route("/account")
@login_required
def account_page():

    customer = get_current_customer()
    account = get_customer_account(customer)
    details = get_customer_details(customer)

    balance = account.balance if account else 0
    account_type = (account.account_type or "savings") if account else "savings"
    account_type_label = account_type.replace("_", " ").title()

    return render_template(
        "account.html",
        balance=balance,
        fname=details.first_name if details else "",
        lname=details.last_name if details else "",
        email=customer.email,
        account_type=account_type_label,
    )


@pages.route("/<operation>")
@login_required
def bank_page(operation):

    valid_operations = {
        "deposit",
        "withdraw",
        "transfer",
        "receipts",
    }

    if operation not in valid_operations:
        abort(404)

    if operation == "receipts":
        return redirect(url_for("pages.receipts"))

    customer = get_current_customer()
    account = get_customer_account(customer)
    account_type = (account.account_type or "savings") if account else "savings"
    account_type_label = account_type.replace("_", " ").title()
    current_balance = account.balance if account else 0
    saved_recipients = []
    if operation == "transfer":
        saved_recipients = (
            Beneficiary.query
            .filter_by(customer_id=customer.customer_id)
            .order_by(Beneficiary.beneficiary_name.asc())
            .all()
        )

    return render_template(
        f"{operation}.html",
        account=account,
        balance=current_balance,
        account_type=account_type_label,
        saved_recipients=saved_recipients,
    )


@pages.route("/transfer/contacts", methods=["POST"])
@login_required
def add_transfer_contact():
    customer = get_current_customer()
    name = (request.form.get("beneficiary_name") or "").strip()
    account_value = (request.form.get("recipient_id") or "").strip()

    if not name or len(name) > 150:
        flash("Enter a contact name (up to 150 characters).", "error")
        return redirect(url_for("pages.bank_page", operation="transfer"))
    try:
        recipient_id = int(account_value)
    except (TypeError, ValueError):
        flash("Enter a valid recipient account ID.", "error")
        return redirect(url_for("pages.bank_page", operation="transfer"))

    recipient_account = db.session.get(Account, recipient_id)
    if (recipient_account is None or recipient_account.status != "active"
            or recipient_account.customer_id == customer.customer_id):
        flash("That active recipient account could not be found.", "error")
        return redirect(url_for("pages.bank_page", operation="transfer"))

    duplicate = Beneficiary.query.filter_by(
        customer_id=customer.customer_id,
        account_number=str(recipient_id),
    ).first()
    if duplicate:
        flash("That recipient is already in your saved contacts.", "error")
        return redirect(url_for("pages.bank_page", operation="transfer"))

    contact = Beneficiary(
        customer_id=customer.customer_id,
        beneficiary_name=name,
        account_number=str(recipient_id),
        bank_name="Coria Bank",
        nickname=name[:50],
    )
    db.session.add(contact)
    db.session.commit()
    flash("Recipient saved to your contacts.", "success")
    return redirect(url_for("pages.bank_page", operation="transfer"))


@pages.route("/transfer/contacts/<int:beneficiary_id>/delete", methods=["POST"])
@login_required
def delete_transfer_contact(beneficiary_id):
    customer = get_current_customer()
    contact = Beneficiary.query.filter_by(
        beneficiary_id=beneficiary_id,
        customer_id=customer.customer_id,
    ).first_or_404()
    db.session.delete(contact)
    db.session.commit()
    flash("Saved recipient removed.", "success")
    return redirect(url_for("pages.bank_page", operation="transfer"))


@pages.route("/receipts")
@login_required
def receipts():

    customer = get_current_customer()
    account = get_customer_account(customer)

    if account is None:
        flash("No bank account is associated with your profile.")
        return redirect(url_for("pages.home"))

    transactions = (
        TransactionList.query
        .filter_by(account_id=account.account_id)
        .order_by(TransactionList.created_at.desc())
        .all()
    )

    account_type = (account.account_type or "savings") if account else "savings"
    account_type_label = account_type.replace("_", " ").title()

    return render_template(
        "receipts.html",
        receipts=transactions,
        account=account,
        account_type=account_type_label,
    )

@pages.route("/notifications")
@login_required
def notifications():
    customer = get_current_customer()

    items = (
        Notification.query
        .filter_by(customer_id=customer.customer_id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    unread_count = sum(1 for item in items if not item.is_read)

    return render_template(
        "notifications.html",
        notifications=items,
        unread_count=unread_count,
        role_name=(customer.role.role_name if customer.role else "customer"),
    )


@pages.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    customer = get_current_customer()

    item = Notification.query.filter_by(
        notification_id=notification_id,
        customer_id=customer.customer_id,
    ).first_or_404()

    item.is_read = True
    db.session.commit()

    flash("Notification marked as read.", "success")
    return redirect(url_for("pages.notifications"))