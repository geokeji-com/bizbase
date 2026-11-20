"""PostgreSQL compatibility patches for Frappe 16.56.0, ERPNext 16.55.0 and CRM 16.0.4.

Production runs on PostgreSQL. These call sites still use MariaDB-only SQL in the pinned
releases and fail on PG:

- ERPNext financial statements force a MariaDB index hint (`FORCE INDEX`) unconditionally.
  Upstream guards it with `frappe.db.db_type == "mariadb"`, as 16.55.0 already does in
  `stock/deprecated_serial_batch.py`.
- Frappe `contact_query` (contact pickers filtered by a linked party) uses `LIMIT a, b` and
  MySQL `if()`; PostgreSQL rejects both (`LIMIT #,# syntax is not supported`).

- ERPNext `item_query` uses the same pagination and ranking syntax, unquoted mixed-case
  table references, and a MariaDB zero date. Preserve the pinned filters, permissions,
  barcode and indexed candidate paths; on PostgreSQL a missing end-of-life date is NULL.

- CRM treats SLA.enabled (smallint on PG) as a boolean WHERE predicate, blocking Lead/Deal saves.

Replacements are written so they run on both MariaDB and PostgreSQL. Each file is checked against
the pinned upstream digest; an already patched file is accepted, anything else stops the build.

Run `python3 pg_compat.py [BENCH_PATH]`. `--check` only reports. No site connection is needed.
"""

import argparse
import hashlib
import stat
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

PATCHES = {
	"apps/crm/crm/fcrm/doctype/crm_service_level_agreement/utils.py": (
		"6fc9444703dd01295eb142281a35a24ba6c6f3d815ad6cd74d157d507a1d9b3d",
		[(".where(SLA.enabled)", ".where(SLA.enabled == 1)")],
	),
	"apps/erpnext/erpnext/accounts/report/financial_statements.py": (
		"74b90b7d0a9947ea66c2467efeb476f681c485c9ea481760f2af4df79ea516fa",
		[
			(
				'\t\tquery = query.force_index("posting_date_company_index")\n',
				'\t\tif frappe.db.db_type == "mariadb":\n'
				'\t\t\tquery = query.force_index("posting_date_company_index")\n',
			),
		],
	),
	"apps/frappe/frappe/contacts/doctype/contact/contact.py": (
		"0d2d444dbd4bee8b001bfec7b4eab92bdbbd720fdc8694daa17a6c4ba54f8674",
		[
			(
				"\t\t\tif(locate(%(_txt)s, `tabContact`.full_name), locate(%(_txt)s, `tabContact`.company_name), 99999),\n",
				"\t\t\tcase when locate(%(_txt)s, `tabContact`.full_name) > 0"
				" then locate(%(_txt)s, `tabContact`.company_name) else 99999 end,\n",
			),
			(
				'\t\tlimit %(start)s, %(page_len)s """,\n',
				'\t\tlimit %(page_len)s offset %(start)s """,\n',
			),
		],
	),
	"apps/erpnext/erpnext/controllers/queries.py": (
		"cb18f8434963b72b5da8d9850d38ffb86de19ba69c828c8d3049407b3416e4ae",
		[
			(
				'\t\tcolumns += """, if(length(tabItem.description) > 40, \\\n\t\t\tconcat(substr(tabItem.description, 1, 40), "..."), description) as description"""',
				'\t\tcolumns += """, case when length(`tabItem`.description) > 40 then\n\t\t\tconcat(substr(`tabItem`.description, 1, 40), \'...\') else description end as description"""',
			),
			(
				'description_cond = "or tabItem.description',
				'description_cond = "or `tabItem`.description',
			),
			('candidate_cond = "and tabItem.name', 'candidate_cond = "and `tabItem`.name'),
			('tabItem.name {columns}\n\t\tfrom tabItem', '`tabItem`.name {columns}\n\t\tfrom `tabItem`'),
			('where tabItem.docstatus', 'where `tabItem`.docstatus'),
			('and tabItem.disabled', 'and `tabItem`.disabled'),
			('and tabItem.has_variants', 'and `tabItem`.has_variants'),
			(
				"and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')",
				'and (`tabItem`.end_of_life > %(today)s or `tabItem`.end_of_life is null {zero_date})',
			),
			('and ({scond} or tabItem.item_code', 'and ({scond} or `tabItem`.item_code'),
			(
				'if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),',
				'coalesce(nullif(locate(%(_txt)s, name), 0), 99999),',
			),
			(
				'if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),',
				'coalesce(nullif(locate(%(_txt)s, item_name), 0), 99999),',
			),
			(
				'limit %(start)s, %(page_len)s """.format(\n\t\t\tcolumns=columns,',
				'limit %(page_len)s offset %(start)s """.format(\n\t\t\tzero_date="or `tabItem`.end_of_life = \'0000-00-00\'" if frappe.db.db_type == "mariadb" else "",\n\t\t\tcolumns=columns,',
			),
			(
				'return f"and tabItem.name in ({allowed_items})"',
				'return f"and `tabItem`.name in ({allowed_items})"',
			),
		],
	),
}


def digest(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def patched(source: str, rules, path: str) -> str:
	for old, new in rules:
		if source.count(old) != 1:
			raise ValueError(f"{path}: expected exactly one occurrence of {old!r}")
		source = source.replace(old, new)
	return source


def plan(bench: Path) -> dict[Path, str | None]:
	"""Return target -> new content, or None when the file is already patched."""
	changes = {}
	for relative, (sha, rules) in PATCHES.items():
		target = bench / relative
		source = target.read_text(encoding="utf-8")
		if digest(source) == sha:
			changes[target] = patched(source, rules, relative)
			continue
		# Already patched: undoing the rules must give back the pinned upstream file.
		original = source
		for old, new in reversed(rules):
			original = original.replace(new, old)
		if digest(original) != sha or patched(original, rules, relative) != source:
			raise ValueError(f"{relative}: unexpected content, not the pinned upstream or its patch")
		changes[target] = None
	return changes


def write(target: Path, text: str) -> None:
	mode = stat.S_IMODE(target.stat().st_mode)
	with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
		handle.write(text)
	tmp = Path(handle.name)
	tmp.chmod(mode)
	tmp.replace(target)


def main(argv=None) -> int:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("bench", nargs="?", default=".", type=Path)
	parser.add_argument("--check", action="store_true", help="report only; exit 1 if a patch is pending")
	args = parser.parse_args(argv)

	changes = plan(args.bench.resolve())
	pending = [target for target, text in changes.items() if text is not None]
	for target, text in changes.items():
		state = "pending" if text is not None else "patched"
		print(f"{state}: {target.relative_to(args.bench.resolve())}")
	if args.check:
		return 1 if pending else 0
	for target in pending:
		write(target, changes[target])
	return 0


if __name__ == "__main__":
	sys.exit(main())
