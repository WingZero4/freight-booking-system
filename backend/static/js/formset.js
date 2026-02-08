/**
 * Django inline formset management for cargo items.
 * Handles adding new rows, marking rows for deletion, and updating TOTAL_FORMS.
 * Formset prefix: 'items'
 *
 * Works with both card-based layout (Phase 1.5) and table-based layout.
 */
document.addEventListener('DOMContentLoaded', function () {
    var PREFIX = 'items';
    var totalFormsInput = document.getElementById('id_' + PREFIX + '-TOTAL_FORMS');
    var container = document.getElementById('cargo-items-container') ||
                    document.getElementById('cargo-items-body');
    var addBtn = document.getElementById('add-item-btn');

    if (!totalFormsInput || !container || !addBtn) {
        return;
    }

    function getTotalForms() {
        return parseInt(totalFormsInput.value, 10);
    }

    function setTotalForms(value) {
        totalFormsInput.value = value;
    }

    /**
     * Add a new empty cargo item by cloning the last row and resetting its values.
     */
    addBtn.addEventListener('click', function () {
        var totalForms = getTotalForms();
        var newIndex = totalForms;

        var rows = container.querySelectorAll('.cargo-item-row');
        if (rows.length === 0) {
            return;
        }

        var lastRow = rows[rows.length - 1];
        var newRow = lastRow.cloneNode(true);

        // Make visible
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

        // Clear validation errors
        var errorDivs = newRow.querySelectorAll('.invalid-feedback, .alert-danger');
        errorDivs.forEach(function (div) {
            div.remove();
        });

        container.appendChild(newRow);
        setTotalForms(newIndex + 1);

        attachRemoveHandler(newRow);
    });

    /**
     * Attach a click handler to the remove button.
     * Marks the row for deletion by checking the DELETE checkbox and hiding it.
     */
    function attachRemoveHandler(row) {
        var removeBtn = row.querySelector('.remove-item-btn');
        if (!removeBtn) {
            return;
        }

        removeBtn.addEventListener('click', function () {
            var deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');

            if (deleteCheckbox) {
                deleteCheckbox.checked = true;
                row.classList.add('d-none');
            } else {
                row.remove();
                reindexForms();
            }
        });
    }

    /**
     * Re-index all form rows after a removal to keep indexes sequential.
     */
    function reindexForms() {
        var rows = container.querySelectorAll('.cargo-item-row');
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
    var existingRows = container.querySelectorAll('.cargo-item-row');
    existingRows.forEach(function (row) {
        attachRemoveHandler(row);
    });
});
