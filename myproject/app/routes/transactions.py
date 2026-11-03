
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from flask import Blueprint, request, redirect, url_for, flash, session
from sqlalchemy import select

from app.extensions import db
from app.models import Account, Customer, TransactionList, TransactionType, Notification

transactions = Blueprint("transactions", __name__)


@transactions.route("/transaction/<operation>", methods=["POST"])
def transaction(operation):
    if operation not in {"deposit", "withdraw", "transfer"}:
        flash("Invalid transaction operation.", "error")
        return redirect(url_for("pages.home"))

    customer_id = session.get("customer_id")

    if customer_id is None:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    try:
        customer_id = UUID(str(customer_id))
    except (ValueError, TypeError, AttributeError):
        session.clear()
        flash("Please log in again.", "error")
        return redirect(url_for("auth.login"))

    customer = db.session.get(Customer, customer_id)
    if customer is None or customer.is_locked or customer.account_status != "active":
        session.clear()
        flash("Your account is unavailable. Please contact support.", "error")
        return redirect(url_for("auth.login"))

    # Return to the page where the transaction was performed.
    def return_to_form():
        return redirect(
            url_for("pages.bank_page", operation=operation)
        )

    try:
        amount = Decimal(request.form.get("amount", "").strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        flash("Please enter a valid amount.", "error")
        return return_to_form()

    if (
        not amount.is_finite()
        or amount <= 0
        or amount.as_tuple().exponent < -2
        or amount >= Decimal("10000000000000")
    ):
        flash(
            "Enter a positive amount with at most two decimal places.",
            "error",
        )
        return return_to_form()

    recipient_id = None

    if operation == "transfer":
        try:
            recipient_id = int(request.form.get("recipient_id", ""))
        except (ValueError, TypeError):
            flash("Please enter a valid recipient account ID.", "error")
            return return_to_form()

    try:
        # Find the logged-in customer's account.
        sender_ref = db.session.execute(
            select(Account.account_id)
            .where(Account.customer_id == customer_id)
            .order_by(Account.account_id)
            .limit(1)
        ).scalar_one_or_none()

        if sender_ref is None:
            flash("No account is associated with your profile.", "error")
            return return_to_form()

        if operation == "transfer" and recipient_id == sender_ref:
            flash("You cannot transfer money to your own account.", "error")
            return return_to_form()

        # Lock accounts in a consistent order for transfers.
        ids_to_lock = (
            sorted([sender_ref, recipient_id])
            if operation == "transfer"
            else [sender_ref]
        )

        locked_accounts = db.session.execute(
            select(Account)
            .where(Account.account_id.in_(ids_to_lock))
            .order_by(Account.account_id)
            .with_for_update()
        ).scalars().all()

        account_map = {
            account.account_id: account
            for account in locked_accounts
        }

        sender = account_map.get(sender_ref)

        # 1. Verify that the sender account exists
        if sender is None:
            db.session.rollback()
            flash("Your account could not be verified.", "error")
            return return_to_form()

        if str(sender.customer_id) != str(customer_id):
            db.session.rollback()
            flash("Your account could not be verified.", "error")
            return return_to_form()

        # 2. Verify account status
        if sender.status != "active":
            db.session.rollback()
            flash(
                "Your account is not active. Transactions are unavailable.",
                "error"
            )
            return return_to_form()

        # 3. Check withdrawal balance
        if operation == "withdraw" and sender.balance < amount:
            db.session.rollback()
            flash("Insufficient funds.", "error")
            return return_to_form()


        if operation == "deposit":
            balance_before = sender.balance
            sender.balance += amount

            db.session.add(
                TransactionList(
                    account_id=sender.account_id,
                    reference_number=str(uuid4()),
                    transaction_type="deposit",
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=sender.balance,
                    description="Cash deposit",
                    status="completed"
                )
            )

        elif operation == "withdraw":
            if sender.balance < amount:
                db.session.rollback()
                flash("Insufficient funds.", "error")
                return return_to_form()

            balance_before = sender.balance
            sender.balance -= amount

            db.session.add(
                TransactionList(
                    account_id=sender.account_id,
                    reference_number=str(uuid4()),
                    transaction_type="withdrawal",
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=sender.balance,
                    description="Cash withdrawal",
                    status="completed"
                )
            )

        else:
            recipient = account_map.get(recipient_id)

            if recipient is None:
                db.session.rollback()
                flash("Recipient account not found.", "error")
                return return_to_form()

            if recipient.status != "active":
                db.session.rollback()
                flash("Recipient account is not active.", "error")
                return return_to_form()

            if sender.balance < amount:
                db.session.rollback()
                flash("Insufficient funds.", "error")
                return return_to_form()

            sender_before = sender.balance
            recipient_before = recipient.balance

            sender.balance -= amount
            recipient.balance += amount

            db.session.add_all([
                TransactionList(
                    account_id=sender.account_id,
                    reference_number=str(uuid4()),
                    transaction_type="transfer_out",
                    amount=amount,
                    balance_before=sender_before,
                    balance_after=sender.balance,
                    description=f"Money transfer sent to account #{recipient.account_id}",
                    status="completed"
                ),
                TransactionList(
                    account_id=recipient.account_id,
                    reference_number=str(uuid4()),
                    transaction_type="transfer_in",
                    amount=amount,
                    balance_before=recipient_before,
                    balance_after=recipient.balance,
                    description=f"Money transfer received from account #{sender.account_id}",
                    status="completed"
                )
            ])

        # Create a notification only after the transaction logic succeeds.
        notification_details = {
            "deposit": (
                "Deposit successful",
                f"Your deposit of ₱{amount:,.2f} was successful."
            ),
            "withdraw": (
                "Withdrawal successful",
                f"Your withdrawal of ₱{amount:,.2f} was successful."
            ),
            "transfer": (
                "Transfer successful",
                f"Your transfer of ₱{amount:,.2f} was successful."
            ),
        }

        title, message = notification_details[operation]

        db.session.add(
            Notification(
                customer_id=customer_id,
                title=title,
                message=message,
                notification_type=operation,
                is_read=False,
            )
        )

        db.session.commit()
        flash("Transaction completed successfully.", "success")

    except Exception:
        db.session.rollback()
        raise

    # Return to the same operation page after success.
    return return_to_form()
