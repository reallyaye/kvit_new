from database import get_db


class ReconcileService:
    """Сервис для сверки реестра лицевых счетов и загруженных квитанций."""

    @staticmethod
    def get_reconciliation_data(filt: str = 'without', period_filter: str = '', page_num: int = 1, per_page: int = 50):
        con = get_db()
        try:
            all_periods = con.execute('SELECT DISTINCT period FROM receipts ORDER BY period').fetchall()
            total_accounts = con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]

            if period_filter:
                total_receipts = con.execute(
                    'SELECT COUNT(*) FROM receipts WHERE period = ?', (period_filter,)
                ).fetchone()[0]
                matched = con.execute('''
                    SELECT COUNT(DISTINCT a.account_number)
                    FROM accounts a JOIN receipts r ON r.account_number = a.account_number
                    WHERE r.period = ?
                ''', (period_filter,)).fetchone()[0]
                orphans = con.execute('''
                    SELECT COUNT(*) FROM receipts r
                    LEFT JOIN accounts a ON a.account_number = r.account_number
                    WHERE a.id IS NULL AND r.period = ?
                ''', (period_filter,)).fetchone()[0]
            else:
                total_receipts = con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
                matched = con.execute('''
                    SELECT COUNT(DISTINCT a.account_number)
                    FROM accounts a JOIN receipts r ON r.account_number = a.account_number
                ''').fetchone()[0]
                orphans = con.execute('''
                    SELECT COUNT(*) FROM receipts r
                    LEFT JOIN accounts a ON a.account_number = r.account_number
                    WHERE a.id IS NULL
                ''').fetchone()[0]

            unmatched_count = total_accounts - matched
            page_num = max(1, int(page_num or 1))
            per_page = max(1, int(per_page or 50))
            offset = (page_num - 1) * per_page

            if filt == 'with':
                if period_filter:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        JOIN receipts r ON r.account_number = a.account_number
                        WHERE r.period = ?
                    ''', (period_filter,)).fetchone()[0]
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        JOIN receipts r ON r.account_number = a.account_number
                    ''').fetchone()[0]

                query = ('''
                    SELECT a.account_number, a.customer_name, a.address, r.period, r.pdf_file
                    FROM accounts a
                    JOIN receipts r ON r.account_number = a.account_number
                    ''' + ('WHERE r.period = ? ' if period_filter else '') + '''
                    ORDER BY a.account_number, r.period DESC
                    LIMIT ? OFFSET ?
                ''')  # nosec B608 - параметризованный запрос
                params = (period_filter, per_page, offset) if period_filter else (per_page, offset)
            elif filt == 'without':
                list_count = unmatched_count
                if period_filter:
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address, NULL as period, NULL as pdf_file
                        FROM accounts a
                        WHERE a.account_number NOT IN (
                            SELECT r.account_number FROM receipts r WHERE r.period = ?
                        )
                        ORDER BY a.account_number
                        LIMIT ? OFFSET ?
                    '''
                    params = (period_filter, per_page, offset)
                else:
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address, NULL as period, NULL as pdf_file
                        FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                        WHERE r.id IS NULL
                        ORDER BY a.account_number
                        LIMIT ? OFFSET ?
                    '''
                    params = (per_page, offset)
            elif filt == 'orphans':
                list_count = orphans
                query = ('''
                    SELECT r.account_number, NULL as customer_name, NULL as address, r.period, r.pdf_file
                    FROM receipts r
                    LEFT JOIN accounts a ON a.account_number = r.account_number
                    WHERE a.id IS NULL ''' + ('AND r.period = ? ' if period_filter else '') + '''
                    ORDER BY r.account_number, r.period DESC
                    LIMIT ? OFFSET ?
                ''')  # nosec B608 - параметризованный запрос
                params = (period_filter, per_page, offset) if period_filter else (per_page, offset)
            else:  # all
                if period_filter:
                    list_count = total_accounts
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                    ''').fetchone()[0]

                query = ('''
                    SELECT a.account_number, a.customer_name, a.address, r.period, r.pdf_file
                    FROM accounts a
                    LEFT JOIN receipts r ON r.account_number = a.account_number ''' + ('AND r.period = ? ' if period_filter else '') + '''
                    ORDER BY a.account_number, r.period DESC
                    LIMIT ? OFFSET ?
                ''')  # nosec B608 - параметризованный запрос
                params = (period_filter, per_page, offset) if period_filter else (per_page, offset)

            rows = con.execute(query, params).fetchall()

            return {
                'all_periods': all_periods,
                'total_accounts': total_accounts,
                'total_receipts': total_receipts,
                'matched': matched,
                'unmatched': unmatched_count,
                'orphans': orphans,
                'list_count': list_count,
                'rows': rows,
                'page_num': page_num,
                'per_page': per_page,
                'filt': filt,
                'period_filter': period_filter
            }
        finally:
            con.close()

reconcile_service = ReconcileService()
