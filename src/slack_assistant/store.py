from datetime import date, datetime

import psycopg

SCHEMA = """
create table if not exists reports (
    report_date date primary key,
    posted_at timestamptz not null,
    kind text not null,
    body text not null
)
"""


class PgStore:
    def __init__(self, url: str):
        self.conn = psycopg.connect(url)
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA)
        self.conn.commit()

    def get_report(self, day: date):
        with self.conn.cursor() as cur:
            cur.execute(
                "select kind, body from reports where report_date = %s",
                (day,),
            )
            return cur.fetchone()

    def save_report(self, day: date, kind: str, body: str, posted_at: datetime):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into reports (report_date, posted_at, kind, body)
                values (%s, %s, %s, %s)
                on conflict (report_date) do update
                set posted_at = excluded.posted_at,
                    kind = excluded.kind,
                    body = excluded.body
                """,
                (day, posted_at, kind, body),
            )
        self.conn.commit()

    def close(self):
        self.conn.close()
