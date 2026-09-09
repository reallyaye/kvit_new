from database import get_db


class ReconcileService:
    """Сервис для сверки реестра лицевых счетов и загруженных квитанций."""

    @staticmethod
    def get_reconciliation_data(
        filt: str = 'without',
        period_filter: str = '',
        page_num: int = 1,
        per_page: int = 50,
        account_query: str = '',
    ):
        con = get_db()
        try:
            account_query = str(account_query or '').strip()[:64]
            account_params = (account_query, account_query)

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
                        WHERE r.period = ? AND (? = '' OR a.account_number = ?)
                    ''', (period_filter, *account_params)).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               r.period, r.pdf_file, r.access_token
                        FROM accounts a
                        JOIN receipts r ON r.account_number = a.account_number
                        WHERE r.period = ? AND (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (period_filter, *account_params, per_page, offset)
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        JOIN receipts r ON r.account_number = a.account_number
                        WHERE (? = '' OR a.account_number = ?)
                    ''', account_params).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               r.period, r.pdf_file, r.access_token
                        FROM accounts a
                        JOIN receipts r ON r.account_number = a.account_number
                        WHERE (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (*account_params, per_page, offset)
            elif filt == 'without':
                if period_filter:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        WHERE a.account_number NOT IN (
                            SELECT r.account_number FROM receipts r WHERE r.period = ?
                        ) AND (? = '' OR a.account_number = ?)
                    ''', (period_filter, *account_params)).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               NULL as period, NULL as pdf_file, NULL as access_token
                        FROM accounts a
                        WHERE a.account_number NOT IN (
                            SELECT r.account_number FROM receipts r WHERE r.period = ?
                        ) AND (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number
                        LIMIT ? OFFSET ?
                    '''
                    params = (period_filter, *account_params, per_page, offset)
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                        WHERE r.id IS NULL AND (? = '' OR a.account_number = ?)
                    ''', account_params).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               NULL as period, NULL as pdf_file, NULL as access_token
                        FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                        WHERE r.id IS NULL AND (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number
                        LIMIT ? OFFSET ?
                    '''
                    params = (*account_params, per_page, offset)
            elif filt == 'orphans':
                if period_filter:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM receipts r
                        LEFT JOIN accounts a ON a.account_number = r.account_number
                        WHERE a.id IS NULL AND r.period = ?
                          AND (? = '' OR r.account_number = ?)
                    ''', (period_filter, *account_params)).fetchone()[0]
                    query = '''
                        SELECT r.account_number, NULL as customer_name, NULL as address,
                               r.period, r.pdf_file, r.access_token
                        FROM receipts r
                        LEFT JOIN accounts a ON a.account_number = r.account_number
                        WHERE a.id IS NULL AND r.period = ?
                          AND (? = '' OR r.account_number = ?)
                        ORDER BY r.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (period_filter, *account_params, per_page, offset)
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM receipts r
                        LEFT JOIN accounts a ON a.account_number = r.account_number
                        WHERE a.id IS NULL AND (? = '' OR r.account_number = ?)
                    ''', account_params).fetchone()[0]
                    query = '''
                        SELECT r.account_number, NULL as customer_name, NULL as address,
                               r.period, r.pdf_file, r.access_token
                        FROM receipts r
                        LEFT JOIN accounts a ON a.account_number = r.account_number
                        WHERE a.id IS NULL AND (? = '' OR r.account_number = ?)
                        ORDER BY r.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (*account_params, per_page, offset)
            else:  # all
                if period_filter:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        WHERE (? = '' OR a.account_number = ?)
                    ''', account_params).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               r.period, r.pdf_file, r.access_token
                        FROM accounts a
                        LEFT JOIN receipts r
                          ON r.account_number = a.account_number AND r.period = ?
                        WHERE (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (period_filter, *account_params, per_page, offset)
                else:
                    list_count = con.execute('''
                        SELECT COUNT(*) FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                        WHERE (? = '' OR a.account_number = ?)
                    ''', account_params).fetchone()[0]
                    query = '''
                        SELECT a.account_number, a.customer_name, a.address,
                               r.period, r.pdf_file, r.access_token
                        FROM accounts a
                        LEFT JOIN receipts r ON r.account_number = a.account_number
                        WHERE (? = '' OR a.account_number = ?)
                        ORDER BY a.account_number, r.period DESC
                        LIMIT ? OFFSET ?
                    '''
                    params = (*account_params, per_page, offset)

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
                'period_filter': period_filter,
                'account_query': account_query,
            }
        finally:
            con.close()


reconcile_service = ReconcileService()
