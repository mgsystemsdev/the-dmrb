# Verify import (SQL)

Run these from the **repo root** (DMRB). The whole line is one command: `sqlite3` + db path + query in double quotes.

**1. Recent import batches**  
(`import_batch` has: batch_id, report_type, checksum, source_file_name, record_count, status, imported_at — no applied_count/conflict_count in DB)

```bash
sqlite3 the-dmrb/data/cockpit.db "SELECT batch_id, report_type, status, record_count, imported_at FROM import_batch ORDER BY batch_id DESC LIMIT 5;"
```

**2. Turnover count**
```bash
sqlite3 the-dmrb/data/cockpit.db "SELECT COUNT(*) FROM turnover;"
```

**3. Latest turnovers**
```bash
sqlite3 the-dmrb/data/cockpit.db "SELECT turnover_id, unit_id, move_out_date, move_in_date, report_ready_date FROM turnover ORDER BY turnover_id DESC LIMIT 5;"
```

**4. Per-row import result for a batch** (replace `1` with your batch_id)
```bash
sqlite3 the-dmrb/data/cockpit.db "SELECT batch_id, unit_code_norm, validation_status, conflict_reason FROM import_row WHERE batch_id = 1;"
```

**Interactive mode** (multiple queries):
```bash
sqlite3 the-dmrb/data/cockpit.db
```
Then type SQL and press Enter; end with `.quit` to exit.
