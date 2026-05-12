import frappe
import traceback
from frappe.utils import flt


@frappe.whitelist()
def check_count():
	results = {"duplicates": [], "missing_payment": [], "overpaid": [], "amount_mismatch": []}

	dupes = frappe.db.sql(
		"""
        SELECT reference_no, COUNT(*) as pe_count,
               GROUP_CONCAT(name ORDER BY creation ASC) as payment_entries,
               SUM(paid_amount) as total_paid
        FROM `tabPayment Entry`
        WHERE reference_no IS NOT NULL
        AND reference_no LIKE 'REC-%'
        AND docstatus = 1
        GROUP BY reference_no
        HAVING COUNT(*) > 1
        ORDER BY reference_no
    """,
		as_dict=True,
	)

	for d in dupes:
		pe_list = d.payment_entries.split(",")
		rec = (
			frappe.db.get_value(
				"Receipting", d.reference_no, ["student_name", "date", "total_allocated"], as_dict=True
			)
			or {}
		)
		results["duplicates"].append(
			{
				"receipt": d.reference_no,
				"student": rec.get("student_name", ""),
				"date": str(rec.get("date", "")),
				"receipt_amount": flt(rec.get("total_allocated", 0)),
				"pe_count": d.pe_count,
				"keep": pe_list[0],
				"cancel": pe_list[1:],
				"total_paid": flt(d.total_paid),
			}
		)

	missing = frappe.db.sql(
		"""
        SELECT r.name, r.date, r.student_name, r.total_allocated
        FROM `tabReceipting` r
        WHERE r.docstatus = 1
        AND NOT EXISTS (
            SELECT 1 FROM `tabPayment Entry` pe
            WHERE pe.reference_no = r.name AND pe.docstatus = 1
        )
        ORDER BY r.date
    """,
		as_dict=True,
	)

	for m in missing:
		results["missing_payment"].append(
			{
				"receipt": m.name,
				"date": str(m.date),
				"student": m.student_name,
				"amount": flt(m.total_allocated),
			}
		)

	overpaid = frappe.db.sql(
		"""
        SELECT pe.name as pe_name, pe.reference_no, pe.paid_amount,
               r.total_allocated as receipt_amount
        FROM `tabPayment Entry` pe
        JOIN `tabReceipting` r ON r.name = pe.reference_no
        WHERE pe.paid_amount > r.total_allocated
        AND pe.docstatus = 1
    """,
		as_dict=True,
	)

	for o in overpaid:
		results["overpaid"].append(
			{
				"pe_name": o.pe_name,
				"receipt_ref": o.reference_no,
				"paid_amount": flt(o.paid_amount),
				"receipt_amount": flt(o.receipt_amount),
				"difference": flt(o.paid_amount) - flt(o.receipt_amount),
			}
		)

	mismatch = frappe.db.sql(
		"""
        SELECT pe.name as pe_name, pe.reference_no, pe.paid_amount,
               r.total_allocated as receipt_amount
        FROM `tabPayment Entry` pe
        JOIN `tabReceipting` r ON r.name = pe.reference_no
        WHERE pe.paid_amount != r.total_allocated
        AND pe.docstatus = 1
    """,
		as_dict=True,
	)

	for m in mismatch:
		results["amount_mismatch"].append(
			{
				"receipt": m.reference_no,
				"receipt_amount": flt(m.receipt_amount),
				"pe_amount": flt(m.paid_amount),
				"difference": flt(m.paid_amount) - flt(m.receipt_amount),
			}
		)

	return results


@frappe.whitelist()
def get_counts():
	try:
		counts = {
			"receipts": {
				"draft": frappe.db.count("Receipting", {"docstatus": 0}),
				"submitted": frappe.db.count("Receipting", {"docstatus": 1}),
				"cancelled": frappe.db.count("Receipting", {"docstatus": 2}),
			},
			"payment_entries": {
				"draft": frappe.db.count("Payment Entry", {"docstatus": 0}),
				"submitted": frappe.db.count("Payment Entry", {"docstatus": 1}),
				"cancelled": frappe.db.count("Payment Entry", {"docstatus": 2}),
			},
		}
		counts["receipts"]["total"] = sum(counts["receipts"].values())
		counts["payment_entries"]["total"] = sum(counts["payment_entries"].values())
		return {"success": True, "counts": counts}
	except Exception as e:
		frappe.log_error(traceback.format_exc(), "get_counts failed")
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def cancel_all_payment_entries():
	try:
		payments = frappe.get_all(
			"Payment Entry", filters={"docstatus": 1}, fields=["name"], order_by="creation asc"
		)
		cancelled = 0
		failed = []
		BATCH = 20

		for i, p in enumerate(payments):
			try:
				doc = frappe.get_doc("Payment Entry", p.name)
				doc.cancel()
				cancelled += 1
			except Exception as e:
				frappe.log_error(
					f"Failed to cancel Payment Entry {p.name}: {str(e)}\n{traceback.format_exc()}",
					"cancel_all_payment_entries",
				)
				failed.append({"name": p.name, "error": str(e)})
				frappe.db.rollback()
				continue

			# Commit every BATCH records to avoid giant transactions
			if (i + 1) % BATCH == 0:
				frappe.db.commit()

		frappe.db.commit()  # final commit for remainder
		return {"success": True, "cancelled": cancelled, "failed_count": len(failed), "failed": failed}
	except Exception as e:
		frappe.log_error(traceback.format_exc(), "cancel_all_payment_entries outer")
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def cancel_all_receiptings():
	try:
		receipts = frappe.get_all(
			"Receipting", filters={"docstatus": 1}, fields=["name"], order_by="creation asc"
		)
		cancelled = 0
		failed = []
		BATCH = 20

		for i, r in enumerate(receipts):
			try:
				doc = frappe.get_doc("Receipting", r.name)
				doc.cancel()
				cancelled += 1
			except Exception as e:
				frappe.log_error(
					f"Failed to cancel Receipting {r.name}: {str(e)}\n{traceback.format_exc()}",
					"cancel_all_receiptings",
				)
				failed.append({"name": r.name, "error": str(e)})
				frappe.db.rollback()
				continue

			if (i + 1) % BATCH == 0:
				frappe.db.commit()

		frappe.db.commit()
		return {"success": True, "cancelled": cancelled, "failed_count": len(failed), "failed": failed}
	except Exception as e:
		frappe.log_error(traceback.format_exc(), "cancel_all_receiptings outer")
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def check_deleted_receipts():
	try:
		deleted = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": "Receipting"},
			fields=["name", "deleted_name", "creation"],
			order_by="creation desc",
		)
		return {"success": True, "count": len(deleted), "deleted": deleted}
	except Exception as e:
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def restore_deleted_receipts():
	import json

	try:
		deleted = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": "Receipting"},
			fields=["name", "deleted_name", "data"],
		)
		restored = []
		for d in deleted:
			try:
				if frappe.db.exists("Receipting", d.deleted_name):
					# Already exists, just clean up trash entry
					frappe.delete_doc("Deleted Document", d.name, force=True)
					continue

				if not d.data:
					continue

				# Parse JSON data
				doc_dict = json.loads(d.data)
				if isinstance(doc_dict, str):
					doc_dict = json.loads(doc_dict)

				# Create a fresh doc and copy data
				new_doc = frappe.get_doc(doc_dict)
				new_doc.name = d.deleted_name

				# Use db_insert to bypass all validations and preserve original docstatus (e.g. Cancelled)
				new_doc.db_insert()

				# Manually insert child table rows
				for table_field in new_doc.meta.get_table_fields():
					for row in new_doc.get(table_field.fieldname):
						row.db_insert()

				# Remove from trash now that it is restored
				frappe.delete_doc("Deleted Document", d.name, force=True)
				restored.append(d.deleted_name)

			except Exception as e:
				# Shorten title to avoid 'Value too big' error (max 140 chars)
				title = f"Restore failed: {d.deleted_name}"
				frappe.log_error(
					title=title,
					message=f"Restore failed for {d.deleted_name}: {str(e)}\n{traceback.format_exc()}",
					reference_doctype="Receipting",
					reference_name=d.deleted_name
				)
				continue

		frappe.db.commit()
		return {"success": True, "count": len(restored), "restored": restored}
	except Exception as e:
		frappe.db.rollback()
		return {"success": False, "message": str(e)}



@frappe.whitelist()
def redo_all_receiptings():
	# Use in_patch to bypass timestamp checks and other non-critical validations
	frappe.flags.in_patch = True
	
	try:
		# Use SQL to discover the correct field name for "Paid Amount"
		# Often it is paid_amt, amount_paid, or total_amount
		meta = frappe.get_meta("Receipting")
		paid_field = None
		
		# 1. Search by Label
		for f in meta.fields:
			if f.label and f.label.lower() == "paid amount":
				paid_field = f.fieldname
				break
		
		# 2. Search by mandatory status and name pattern if label search fails
		if not paid_field:
			for f in meta.fields:
				if f.reqd and ("paid" in f.fieldname.lower() or "amount" in f.fieldname.lower()):
					paid_field = f.fieldname
					break
		
		# 3. Last resort fallbacks
		if not paid_field:
			for f_name in ["paid_amt", "amount_paid", "total_amount", "amount", "total_allocated"]:
				if meta.has_field(f_name):
					paid_field = f_name
					break
		
		if not paid_field:
			paid_field = "paid_amount" # Final fallback

		# Force update modified timestamps to now to avoid 'Document has been modified' errors
		frappe.db.sql("UPDATE `tabReceipting` SET modified = NOW() WHERE docstatus = 2")
		frappe.db.sql("UPDATE `tabReceipt Item` SET modified = NOW() WHERE parent IN (SELECT name FROM `tabReceipting` WHERE docstatus = 2)")
		frappe.db.commit()

		# Use SQL to get the names of cancelled original receipts (not amendments)
		recs = frappe.db.sql(
			"""
			SELECT name FROM `tabReceipting` 
			WHERE docstatus = 2 AND (amended_from IS NULL OR amended_from = '')
			ORDER BY creation ASC
		""",
			as_dict=True,
		)

		redone = []
		skipped = []
		failed = []
		BATCH = 1

		for r in recs:
			name = r["name"]
			try:
				# 1. Fetch full original document data
				if not frappe.db.exists("Receipting", name):
					continue
				
				orig_doc = frappe.get_doc("Receipting", name)

				# Skip if no money is being receipted
				# Use discovered paid_field or total_allocated as backup
				paid_val = flt(orig_doc.get(paid_field) or orig_doc.get("total_allocated") or 0)
				if paid_val <= 0:
					skipped.append({"name": name, "reason": f"Amount is 0 (checked field: {paid_field})"})
					continue

				# 2. Cleanup any blocking amendment records
				am_name = name + "-1"
				if frappe.db.exists("Receipting", am_name):
					am_status = frappe.db.get_value("Receipting", am_name, "docstatus")
					if am_status == 1:
						frappe.get_doc("Receipting", am_name).cancel()
					frappe.delete_doc("Receipting", am_name, force=True)

				# 3. Prepare data for a clean DB insert
				doc_data = orig_doc.as_dict()
				
				# DEEP CLEAN: Remove metadata/timestamps
				system_fields = ["name", "modified", "modified_by", "creation", "owner", "docstatus", "amended_from", "payment_entry", "parent", "parentfield", "parenttype", "idx"]
				
				for key in system_fields:
					if key in doc_data: del doc_data[key]
				
				# Clean child tables recursively
				for fieldname, value in doc_data.items():
					if isinstance(value, list): # Likely a child table
						for row in value:
							if isinstance(row, dict):
								for key in system_fields:
									if key in row: del row[key]
				
				# 4. Hard delete the original record to ensure the name is absolutely free
				frappe.db.sql("DELETE FROM `tabReceipting` WHERE name = %s", name)
				frappe.db.sql("DELETE FROM `tabReceipt Item` WHERE parent = %s", name)

				# 5. Low-level DB Insert (Bypasses version checks and object cache)
				new_doc = frappe.get_doc(doc_data)
				new_doc.name = name
				new_doc.docstatus = 0
				
				# Reinforce mandatory paid field using discovered name
				new_doc.set(paid_field, paid_val)

				# Use db_insert for the parent
				new_doc.db_insert()
				
				# Force set paid field via direct SQL to be absolutely certain
				frappe.db.sql(f"UPDATE `tabReceipting` SET `{paid_field}` = %s WHERE name = %s", (paid_val, name))

				# Use db_insert for child rows
				if new_doc.get("invoice"):
					for row in new_doc.invoice:
						row.parent = name
						row.parenttype = "Receipting"
						row.parentfield = "invoice"
						row.db_insert()

				# 6. Fetch FRESH and Submit
				fresh_doc = frappe.get_doc("Receipting", name)
				fresh_doc.flags.ignore_validate = True
				fresh_doc.set(paid_field, paid_val)
				fresh_doc.submit()

				# 7. Verify Payment Entry
				pe_name = frappe.db.get_value(
					"Payment Entry", {"reference_no": fresh_doc.name, "docstatus": ["!=", 2]}, "name"
				)

				redone.append(
					{
						"receipt": name,
						"payment_entry": pe_name,
						"amount": fresh_doc.total_allocated,
						"student": fresh_doc.student_name,
					}
				)

			except Exception as e:
				frappe.db.rollback()
				err_str = str(e)
				if "DuplicateEntryError" in err_str or "Duplicate entry" in err_str:
					skipped.append({"name": name, "reason": "Duplicate entry found during insertion"})
				elif "mandatory" in err_str.lower():
					skipped.append({"name": name, "reason": f"Validation failed: {err_str}"})
				else:
					failed.append({"name": name, "error": err_str})
					frappe.log_error(
						f"Redo failed for {name}: {err_str}\n{traceback.format_exc()}", "redo_all_receiptings"
					)
				continue

			if (len(redone) + len(failed) + len(skipped)) % BATCH == 0:
				frappe.db.commit()

		frappe.db.commit()
		return {
			"success": True,
			"redone_count": len(redone),
			"skipped_count": len(skipped),
			"failed_count": len(failed),
			"redone": redone,
			"skipped": skipped,
			"failed": failed,
			"discovered_paid_field": paid_field
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(traceback.format_exc(), "redo_all_receiptings outer")
		return {"success": False, "message": str(e)}
