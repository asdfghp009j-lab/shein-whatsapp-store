from __future__ import annotations

from datetime import datetime, timezone

from database import log_event


def build_salary_deduction(db, supervisor_id: int, settings: dict, environment: str = "LIVE"):
    threshold = max(1, int(settings.get("negative_threshold", "5")))
    deduction = float(settings.get("deduction_sar", "350"))

    ratings = db.execute(
        """
        SELECT id, supervisor_rating FROM ratings
        WHERE supervisor_id = ? AND eligible = 1 AND environment = ? AND supervisor_rating <= 2
        ORDER BY id
        """,
        (supervisor_id, environment),
    ).fetchall()

    if len(ratings) < threshold:
        return 0

    batches = []
    for index in range(0, len(ratings) - threshold + 1, threshold):
        batch = ratings[index:index + threshold]
        batches.append((batch[0]["id"], batch[-1]["id"]))

    applied = 0
    for start_id, end_id in batches:
        exists = db.execute(
            "SELECT id FROM salary_transactions WHERE supervisor_id = ? AND rating_batch_start = ? AND rating_batch_end = ? AND environment = ?",
            (supervisor_id, start_id, end_id, environment),
        ).fetchone()
        if exists:
            continue

        ref = f"SAL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{supervisor_id}-{start_id}"
        db.execute(
            "INSERT INTO salary_transactions(transaction_ref, supervisor_id, kind, amount_sar, rating_batch_start, rating_batch_end, period, approved, environment, reason, created_at) VALUES (?, ?, 'deduction', ?, ?, ?, ?, 1, ?, ?, ?)",
            (ref, supervisor_id, deduction, start_id, end_id, datetime.now(timezone.utc).strftime("%Y-%m"), environment, f"خصم تلقائي بعد {threshold} تقييمات سلبية مؤهلة", datetime.now(timezone.utc).isoformat()),
        )
        applied += 1
        log_event(db, None, "salary_deduction", "salary", ref, f"supervisor_id={supervisor_id}; amount={deduction}")

    return applied


def monthly_salary_summary(db, supervisor_id: int, settings: dict):
    base_salary = float(settings.get("salary_base_sar", "1000"))
    deductions = db.execute(
        "SELECT COALESCE(SUM(amount_sar), 0) AS total FROM salary_transactions WHERE supervisor_id = ? AND kind = 'deduction' AND approved = 1",
        (supervisor_id,),
    ).fetchone()["total"]
    bonuses = db.execute(
        "SELECT COALESCE(SUM(amount_sar), 0) AS total FROM salary_transactions WHERE supervisor_id = ? AND kind = 'bonus' AND approved = 1",
        (supervisor_id,),
    ).fetchone()["total"]
    net = base_salary - deductions + bonuses
    return {
        "base_salary": base_salary,
        "deductions": float(deductions),
        "bonus": float(bonuses),
        "net": max(0.0, net),
    }
