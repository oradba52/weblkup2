"""Первая миграция: все таблицы + индексы.

revision: 0001
revises:
create_date: 2026-10-30

Создаёт полный набор таблиц:
- users (админ-аккаунты)
- login_log (логи входов)
- person (заказчики)
- catalog (каталог товара)
- booking (прокат)
- sale (продажа)

Все индексы создаются в этой же миграции.
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # --- login_log ---
    op.create_table(
        "login_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_login_log_user", "login_log", ["user_id"])
    op.create_index("idx_login_log_created", "login_log", ["created_at"])

    # --- person ---
    op.create_table(
        "person",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("second_name", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("telegram_id", sa.Integer, nullable=True, unique=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_person_phone", "person", ["phone"])
    op.create_index("idx_person_telegram", "person", ["telegram_id"])

    # --- catalog ---
    op.create_table(
        "catalog",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("type", sa.String(10), nullable=False, server_default="rent"),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("is_sold", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_catalog_size", "catalog", ["size"])
    op.create_index("idx_catalog_price", "catalog", ["price"])
    op.create_index("idx_catalog_name", "catalog", ["name"])
    op.create_index("idx_catalog_type", "catalog", ["type"])

    # --- booking ---
    op.create_table(
        "booking",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_start", sa.Date, nullable=False),
        sa.Column("data_finish", sa.Date, nullable=False),
        sa.Column("fact_finish", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("total_price", sa.Float, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_booking_dates", "booking", ["data_start", "data_finish"])
    op.create_index("idx_booking_person", "booking", ["person_id"])
    op.create_index("idx_booking_catalog", "booking", ["catalog_id"])
    op.create_index("idx_booking_status", "booking", ["status"])

    # --- sale ---
    op.create_table(
        "sale",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("sale_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_sale_date", "sale", ["sale_date"])
    op.create_index("idx_sale_person", "sale", ["person_id"])
    op.create_index("idx_sale_catalog", "sale", ["catalog_id"])


def downgrade() -> None:
    op.drop_table("sale")
    op.drop_table("booking")
    op.drop_table("catalog")
    op.drop_table("person")
    op.drop_table("login_log")
    op.drop_table("users")
