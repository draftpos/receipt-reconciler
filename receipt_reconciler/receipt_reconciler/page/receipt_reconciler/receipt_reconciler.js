frappe.pages['receipt-reconciler'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Receipts & Payments Checker',
        single_column: true
    });

    $(page.body).html(`
        <div style="padding: 20px;">
            <div class="form-group">
                <button id="btn-cancel-pe" class="btn btn-danger btn-sm">Cancel Payment Entries</button>
                <button id="btn-cancel-receipts" class="btn btn-warning btn-sm">Cancel Receipts</button>
                <button id="btn-redo" class="btn btn-success btn-sm">Redo Cancelled Receipts</button>
                <button id="btn-check" class="btn btn-primary btn-sm">Check Errors</button>
                <button id="btn-counts" class="btn btn-info btn-sm">Show Counts</button>
                <button id="btn-check-deleted" class="btn btn-secondary btn-sm">Check Deleted</button>
                <button id="btn-restore" class="btn btn-dark btn-sm">Restore Deleted</button>
            </div>
            <div id="status" style="margin-top: 10px;"></div>
            <div id="results" style="margin-top: 20px;"></div>
        </div>
    `);

    const METHOD_BASE = "receipt_reconciler.receipt_reconciler.page.receipt_reconciler.receipt_reconciler.";

    // Disable all buttons while a call is running
    function setBusy(busy) {
        $('#btn-cancel-pe, #btn-cancel-receipts, #btn-redo, #btn-check, #btn-counts, #btn-check-deleted, #btn-restore')
            .prop('disabled', busy);
    }

    function showError(msg) {
        $('#status').html('<span style="color:red">✗ ' + msg + '</span>');
    }

    $('#btn-check-deleted').on('click', function () {
        setBusy(true);
        $('#status').html('Checking deleted documents...');
        frappe.call({
            method: METHOD_BASE + 'check_deleted_receipts',
            callback: function (r) {
                setBusy(false);
                if (r.message && r.message.success) {
                    var html = '<h4>Deleted Receipts: ' + r.message.count + '</h4>';
                    if (r.message.count > 0) {
                        html += '<pre>' + JSON.stringify(r.message.deleted, null, 2) + '</pre>';
                    } else {
                        html += '<div class="alert alert-info">No deleted receipts found in trash.</div>';
                    }
                    $('#results').html(html);
                }
            }
        });
    });

    $('#btn-restore').on('click', function () {
        frappe.confirm('Restore ALL deleted Receipts from trash?', function () {
            setBusy(true);
            $('#status').html('Restoring receipts...');
            frappe.call({
                method: METHOD_BASE + 'restore_deleted_receipts',
                callback: function (r) {
                    setBusy(false);
                    if (r.message && r.message.success) {
                        var msg = '✓ Restored ' + r.message.count + ' receipts';
                        $('#status').html('<span style="color:green">' + msg + '</span>');
                        if (r.message.restored.length) {
                            $('#results').html('<h5>Restored:</h5><pre>' + JSON.stringify(r.message.restored, null, 2) + '</pre>');
                        }
                    } else {
                        showError(r.message ? r.message.message : 'Unknown error');
                    }
                }
            });
        });
    });

    $('#btn-check').on('click', function () {
        setBusy(true);
        $('#status').html('Checking...');
        frappe.call({
            method: METHOD_BASE + 'check_count',
            freeze: true,
            freeze_message: 'Checking for errors...',
            callback: function (r) {
                setBusy(false);
                if (r.message) {
                    var d = r.message;
                    var html = '<h4>Results:</h4>';
                    var clean = true;

                    if (d.duplicates && d.duplicates.length) {
                        clean = false;
                        html += '<div class="card mb-3"><div class="card-header bg-danger text-white">Duplicates (' + d.duplicates.length + ')</div><div class="card-body"><pre>' + JSON.stringify(d.duplicates, null, 2) + '</pre></div></div>';
                    }
                    if (d.missing_payment && d.missing_payment.length) {
                        clean = false;
                        html += '<div class="card mb-3"><div class="card-header bg-warning">Missing Payment Entries (' + d.missing_payment.length + ')</div><div class="card-body"><pre>' + JSON.stringify(d.missing_payment, null, 2) + '</pre></div></div>';
                    }
                    if (d.overpaid && d.overpaid.length) {
                        clean = false;
                        html += '<div class="card mb-3"><div class="card-header bg-info text-white">Overpaid (' + d.overpaid.length + ')</div><div class="card-body"><pre>' + JSON.stringify(d.overpaid, null, 2) + '</pre></div></div>';
                    }
                    if (d.amount_mismatch && d.amount_mismatch.length) {
                        clean = false;
                        html += '<div class="card mb-3"><div class="card-header bg-primary text-white">Mismatches (' + d.amount_mismatch.length + ')</div><div class="card-body"><pre>' + JSON.stringify(d.amount_mismatch, null, 2) + '</pre></div></div>';
                    }
                    if (clean) html += '<div class="alert alert-success">✓ No issues found</div>';

                    $('#results').html(html);
                    $('#status').html('<span style="color:green">✓ Check complete</span>');
                } else {
                    showError('No response from server');
                }
            },
            error: function (err) {
                setBusy(false);
                showError(JSON.stringify(err));
            }
        });
    });

    $('#btn-counts').on('click', function () {
        setBusy(true);
        $('#status').html('Loading counts...');
        frappe.call({
            method: METHOD_BASE + 'get_counts',
            freeze: true,
            freeze_message: 'Loading counts...',
            callback: function (r) {
                setBusy(false);
                if (r.message && r.message.success) {
                    var c = r.message.counts;
                    var html = '<h4>📊 Summary Counts</h4><table class="table table-bordered">' +
                        '<tr><th>Type</th><th>Draft</th><th>Submitted</th><th>Cancelled</th><th>Total</th></tr>' +
                        '<tr><td><b>Receipts</b></td><td>' + c.receipts.draft + '</td><td style="color:green">' + c.receipts.submitted + '</td><td style="color:#999">' + c.receipts.cancelled + '</td><td><b>' + c.receipts.total + '</b></td></tr>' +
                        '<tr><td><b>Payment Entries</b></td><td>' + c.payment_entries.draft + '</td><td style="color:green">' + c.payment_entries.submitted + '</td><td style="color:#999">' + c.payment_entries.cancelled + '</td><td><b>' + c.payment_entries.total + '</b></td></tr>' +
                        '<tr style="background:#f0f0f0"><td><b>GRAND TOTAL</b></td><td><b>' + (c.receipts.draft + c.payment_entries.draft) + '</b></td><td><b style="color:green">' + (c.receipts.submitted + c.payment_entries.submitted) + '</b></td><td><b style="color:#999">' + (c.receipts.cancelled + c.payment_entries.cancelled) + '</b></td><td><b>' + (c.receipts.total + c.payment_entries.total) + '</b></td></tr>' +
                        '</table>';
                    $('#results').html(html);
                    $('#status').html('<span style="color:green">✓ Counts loaded</span>');
                } else {
                    showError(JSON.stringify(r.message));
                }
            },
            error: function (err) {
                setBusy(false);
                showError(JSON.stringify(err));
            }
        });
    });

    $('#btn-cancel-pe').on('click', function () {
        frappe.confirm(
            'Cancel ALL submitted Payment Entries? This cannot be undone easily.',
            function () {
                setBusy(true);
                $('#status').html('Cancelling Payment Entries...');
                frappe.call({
                    method: METHOD_BASE + 'cancel_all_payment_entries',
                    freeze: true,
                    freeze_message: 'Cancelling payment entries, please wait...',
                    timeout: 600,
                    callback: function (r) {
                        setBusy(false);
                        if (r.message && r.message.success) {
                            var msg = '✓ Cancelled ' + (r.message.cancelled || 0) + ' payment entries';
                            if (r.message.failed_count) {
                                msg += ' | ⚠ ' + r.message.failed_count + ' failed (check Error Log)';
                            }
                            $('#status').html('<span style="color:green">' + msg + '</span>');
                        } else {
                            showError(r.message ? r.message.message : 'Unknown error');
                        }
                    },
                    error: function (err) {
                        setBusy(false);
                        showError(JSON.stringify(err));
                    }
                });
            }
        );
    });

    $('#btn-cancel-receipts').on('click', function () {
        frappe.confirm(
            'Cancel ALL submitted Receipts? This cannot be undone easily.',
            function () {
                setBusy(true);
                $('#status').html('Cancelling Receipts...');
                frappe.call({
                    method: METHOD_BASE + 'cancel_all_receiptings',
                    freeze: true,
                    freeze_message: 'Cancelling receipts, please wait...',
                    timeout: 600,
                    callback: function (r) {
                        setBusy(false);
                        if (r.message && r.message.success) {
                            var msg = '✓ Cancelled ' + (r.message.cancelled || 0) + ' receipts';
                            if (r.message.failed_count) {
                                msg += ' | ⚠ ' + r.message.failed_count + ' failed (check Error Log)';
                            }
                            $('#status').html('<span style="color:green">' + msg + '</span>');
                        } else {
                            showError(r.message ? r.message.message : 'Unknown error');
                        }
                    },
                    error: function (err) {
                        setBusy(false);
                        showError(JSON.stringify(err));
                    }
                });
            }
        );
    });

    $('#btn-redo').on('click', function () {
        frappe.confirm(
            'Redo ALL cancelled receipts and recreate their Payment Entries?',
            function () {
                setBusy(true);
                $('#status').html('Redoing cancelled receipts...');
                frappe.call({
                    method: METHOD_BASE + 'redo_all_receiptings',
                    freeze: true,
                    freeze_message: 'Recreating receipts and payments, please wait...',
                    timeout: 600,
                    callback: function (r) {
                        setBusy(false);
                        if (r.message && r.message.success) {
                            var msg = '✓ Redone ' + (r.message.redone_count || 0) +
                                ' | ⏭ Skipped ' + (r.message.skipped_count || 0) +
                                (r.message.failed_count ? ' | ⚠ ' + r.message.failed_count + ' failed (check Error Log)' : '');
                            $('#status').html('<span style="color:green">' + msg + '</span>');
                            var details = '';
                            if (r.message.failed && r.message.failed.length) {
                                details += '<h5>Failed:</h5><pre>' + JSON.stringify(r.message.failed, null, 2) + '</pre>';
                            }
                            if (r.message.skipped && r.message.skipped.length) {
                                details += '<h5>Skipped:</h5><pre>' + JSON.stringify(r.message.skipped, null, 2) + '</pre>';
                            }
                            if (details) $('#results').html(details);
                        } else {
                            showError(r.message ? r.message.message : 'Unknown error');
                        }
                    },
                    error: function (err) {
                        setBusy(false);
                        showError(JSON.stringify(err));
                    }
                });
            }
        );
    });
};