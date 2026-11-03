from functools import wraps
from uuid import UUID

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import Account, AuditLog, Customer, CustomerDetails, LoginHistory, Role, TransactionList

admin = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        customer_id = session.get("customer_id")
        if not customer_id:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        try:
            customer = db.session.get(Customer, UUID(str(customer_id)))
        except (ValueError, TypeError, AttributeError):
            customer = None
        if (customer is None or customer.is_locked or customer.account_status != "active"):
            session.clear()
            flash("Your account is unavailable. Please log in again.", "error")
            return redirect(url_for("auth.login"))
        if not customer.role or customer.role.role_name.strip().lower() != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def write_audit(action, entity_type=None, entity_id=None, description=None):
    try:
        actor_id = UUID(str(session.get("customer_id")))
        db.session.add(AuditLog(
            customer_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=request.remote_addr,
        ))
    except Exception:
        # Audit logging should not hide the primary operation; callers commit it.
        pass


@admin.route("/")
@admin_required
def dashboard():
    total_customers = Customer.query.count()
    total_accounts = Account.query.count()
    total_transactions = TransactionList.query.count()
    total_balance = db.session.query(func.coalesce(func.sum(Account.balance), 0)).scalar()
    recent_transactions = TransactionList.query.order_by(TransactionList.created_at.desc()).limit(12).all()
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(12).all()
    return render_template(
        "admin.html",
        view_name="dashboard",
        total_customers=total_customers,
        total_accounts=total_accounts,
        total_transactions=total_transactions,
        total_balance=total_balance,
        recent_transactions=recent_transactions,
        recent_logs=recent_logs,
    )


@admin.route("/users")
@admin_required
def users():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    roles = Role.query.order_by(Role.role_name.asc()).all()
    details_by_id = {str(d.customer_id): d for d in CustomerDetails.query.all()}
    accounts_by_customer = {}
    for account in Account.query.order_by(Account.account_id.asc()).all():
        accounts_by_customer.setdefault(str(account.customer_id), []).append(account)
    return render_template(
        "admin.html", view_name="users", customers=customers, roles=roles,
        details_by_id=details_by_id, accounts_by_customer=accounts_by_customer,
    )


@admin.route("/users/<uuid:customer_id>/role", methods=["POST"])
@admin_required
def update_role(customer_id):
    target = db.session.get(Customer, customer_id)
    role_id = request.form.get("role_id", type=int)
    role = db.session.get(Role, role_id) if role_id is not None else None
    if target is None or role is None:
        flash("Customer or role was not found.", "error")
        return redirect(url_for("admin.users"))
    actor_id = UUID(str(session.get("customer_id")))
    if target.customer_id == actor_id and role.role_name.strip().lower() != "admin":
        flash("You cannot remove your own admin role here.", "error")
        return redirect(url_for("admin.users"))
    old_role = target.role.role_name if target.role else "unknown"
    target.role_id = role.role_id
    write_audit(
        "customer_role_changed", "customer", None,
        f"Changed role for username '{target.username}' from '{old_role}' to '{role.role_name}'.",
    )
    try:
        db.session.commit()
        flash(f"Updated {target.username}'s role to {role.role_name}.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not update the role. Please try again.", "error")
    return redirect(url_for("admin.users"))


@admin.route("/users/<uuid:customer_id>/status", methods=["POST"])
@admin_required
def update_account_status(customer_id):
    target = db.session.get(Customer, customer_id)
    new_status = (request.form.get("account_status") or "").strip().lower()
    if target is None:
        flash("Customer was not found.", "error")
        return redirect(url_for("admin.users"))
    if new_status not in {"active", "frozen", "closed"}:
        flash("Choose a valid account status.", "error")
        return redirect(url_for("admin.users"))
    actor_id = UUID(str(session.get("customer_id")))
    if target.customer_id == actor_id and new_status != "active":
        flash("You cannot freeze or close your own administrator account.", "error")
        return redirect(url_for("admin.users"))

    old_status = target.account_status or "active"
    target.account_status = new_status
    # Keep the legacy lock flag synchronized for existing checks/integrations.
    target.is_locked = new_status != "active"
    write_audit(
        "customer_account_status_changed", "customer", str(target.customer_id),
        f"Changed account status for username '{target.username}' from '{old_status}' to '{new_status}'.",
    )
    try:
        db.session.commit()
        flash(f"{target.username}'s account status is now {new_status.title()}.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not update the account status. Please try again.", "error")
    return redirect(url_for("admin.users"))


@admin.route("/transactions")
@admin_required
def transactions():
    items = TransactionList.query.order_by(TransactionList.created_at.desc()).limit(250).all()
    account_ids = {item.account_id for item in items}
    accounts = Account.query.filter(Account.account_id.in_(account_ids)).all() if account_ids else []
    accounts_by_id = {account.account_id: account for account in accounts}
    customers = Customer.query.all()
    customers_by_id = {str(customer.customer_id): customer for customer in customers}
    return render_template(
        "admin.html", view_name="transactions", transactions=items,
        accounts_by_id=accounts_by_id, customers_by_id=customers_by_id,
    )


@admin.route("/audit-logs")
@admin_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(250).all()
    actor_ids = {log.customer_id for log in logs if log.customer_id}
    actors = Customer.query.filter(Customer.customer_id.in_(actor_ids)).all() if actor_ids else []
    actors_by_id = {str(customer.customer_id): customer for customer in actors}
    return render_template("admin.html", view_name="audit", logs=logs, actors_by_id=actors_by_id)


@admin.route("/login-history")
@admin_required
def login_history():
    entries = LoginHistory.query.order_by(LoginHistory.login_time.desc()).limit(250).all()
    return render_template("admin.html", view_name="login_history", entries=entries)
