/**
 * Django inline formset management for cargo items.
 * Handles adding new rows, marking rows for deletion, and updating TOTAL_FORMS.
 * Formset prefix: 'items'
 */
document.addEventListener('DOMContentLoaded', function () {
    const PREFIX = 'items';
    const totalFormsInput = document.getElementById('id_' + PREFIX + '-TOTAL_FORMS');
    const tableBody = document.getElementById('cargo-items-body');
    const addBtn = document.getElementById('add-item-btn');

    if (!totalFormsInput || !tableBody || !addBtn) {
        return;
    }

    /**
     * Get the current total number of forms (including deleted ones).
     */
    function getTotalForms() {
        return parseInt(totalFormsInput.value, 10);
    }

    /**
     * Set the TOTAL_FORMS value.
     */
    function setTotalForms(value) {
        totalFormsInput.value = value;
    }

    /**
     * Add a new empty cargo item row by cloning the last row and resetting its values.
     */
    addBtn.addEventListener('click', function () {
        var totalForms = getTotalForms();
        var newIndex = totalForms;

        // Get all rows to find one to clone as template
        var rows = tableBody.querySelectorAll('tr.cargo-item-row');
        if (rows.length === 0) {
            return;
        }

        // Clone the last row
        var lastRow = rows[rows.length - 1];
        var newRow = lastRow.cloneNode(true);

        // Make visible (in case template row was hidden)
        newRow.classList.remove('d-none');

        // Update all input/select names and ids with the new index
        var fields = newRow.querySelectorAll('input, select, textarea');
        fields.forEach(function (field) {
            if (field.name) {
                field.name = field.name.replace(
                    new RegExp(PREFIX + '-\\d+-'),
                    PREFIX + '-' + newIndex + '-'
                );
            }
            if (field.id) {
                field.id = field.id.replace(
                    new RegExp(PREFIX + '-\\d+-'),
                    PREFIX + '-' + newIndex + '-'
                );
            }

            // Reset field values
            if (field.type === 'checkbox') {
                field.checked = false;
            } else if (field.tagName === 'SELECT') {
                field.selectedIndex = 0;
            } else if (field.type === 'hidden') {
                // Clear hidden id field for new forms (not the DELETE field)
                if (field.name.endsWith('-id')) {
                    field.value = '';
                }
            } else {
                field.value = '';
            }
        });

        // Update labels
        var labels = newRow.querySelectorAll('label');
        labels.forEach(function (label) {
            if (label.htmlFor) {
                label.htmlFor = label.htmlFor.replace(
                    new RegExp(PREFIX + '-\\d+-'),
                    PREFIX + '-' + newIndex + '-'
                );
            }
        });

        // Clear any validation error messages in the new row
        var errorDivs = newRow.querySelectorAll('.invalid-feedback');
        errorDivs.forEach(function (div) {
            div.remove();
        });

        // Append the new row and update form count
        tableBody.appendChild(newRow);
        setTotalForms(newIndex + 1);

        // Attach remove handler to the new row
        attachRemoveHandler(newRow);
    });

    /**
     * Attach a click handler to the remove button in a row.
     * Marks the row for deletion by checking the DELETE checkbox and hiding the row.
     */
    function attachRemoveHandler(row) {
        var removeBtn = row.querySelector('.remove-item-btn');
        if (!removeBtn) {
            return;
        }

        removeBtn.addEventListener('click', function () {
            var deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');

            if (deleteCheckbox) {
                // Existing item: mark for deletion and hide
                deleteCheckbox.checked = true;
                row.classList.add('d-none');
            } else {
                // New item (no DELETE checkbox from Django): just remove the row
                // and update TOTAL_FORMS
                row.remove();
                reindexForms();
            }
        });
    }

    /**
     * Re-index all visible form rows after a removal.
     * This ensures form indexes are sequential.
     */
    function reindexForms() {
        var rows = tableBody.querySelectorAll('tr.cargo-item-row');
        rows.forEach(function (row, index) {
            var fields = row.querySelectorAll('input, select, textarea');
            fields.forEach(function (field) {
                if (field.name) {
                    field.name = field.name.replace(
                        new RegExp(PREFIX + '-\\d+-'),
                        PREFIX + '-' + index + '-'
                    );
                }
                if (field.id) {
                    field.id = field.id.replace(
                        new RegExp(PREFIX + '-\\d+-'),
                        PREFIX + '-' + index + '-'
                    );
                }
            });

            var labels = row.querySelectorAll('label');
            labels.forEach(function (label) {
                if (label.htmlFor) {
                    label.htmlFor = label.htmlFor.replace(
                        new RegExp(PREFIX + '-\\d+-'),
                        PREFIX + '-' + index + '-'
                    );
                }
            });
        });
        setTotalForms(rows.length);
    }

    // Attach remove handlers to all existing rows
    var existingRows = tableBody.querySelectorAll('tr.cargo-item-row');
    existingRows.forEach(function (row) {
        attachRemoveHandler(row);
    });
});
