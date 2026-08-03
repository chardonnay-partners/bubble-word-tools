from ..core.models import SchemaError
from ..core.validation import validate_pool, write_report


def run(store, settings, report_path):
    try:
        pool = store.load_all()
    except SchemaError as error:
        print(f"ERROR {error}")
        return 1
    issues = validate_pool(pool, settings)
    write_report(issues, report_path)
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = len(issues) - error_count
    print(f"{len(pool)} categories, {error_count} errors, {warning_count} warnings")
    print(f"report: {report_path}")
    return 1 if error_count else 0
