(() => {
    const sortableLabels = new Set(["make", "make / model", "company", "manufacturer"]);

    function sortTable(table, header, direction) {
        const body = table.tBodies[0];
        if (!body) return;

        const columnIndex = header.cellIndex;
        const rows = Array.from(body.rows).filter(row => row.cells.length > columnIndex);
        rows.sort((left, right) => {
            const leftValue = left.cells[columnIndex].textContent.trim().toLocaleLowerCase();
            const rightValue = right.cells[columnIndex].textContent.trim().toLocaleLowerCase();
            return direction * leftValue.localeCompare(rightValue, undefined, { numeric: true });
        });

        rows.forEach(row => body.appendChild(row));
        table.querySelectorAll("th[data-sort-direction]").forEach(cell => {
            if (cell !== header) cell.removeAttribute("data-sort-direction");
        });
        header.dataset.sortDirection = direction === 1 ? "ascending" : "descending";
    }

    function updateCompanyOptions(table, select) {
        const makeHeader = Array.from(table.querySelectorAll("thead th")).find(header =>
            sortableLabels.has(header.textContent.trim().toLocaleLowerCase())
        );
        const columnIndex = makeHeader ? makeHeader.cellIndex : -1;
        if (columnIndex < 0 || !table.tBodies[0]) return;

        const companies = Array.from(table.tBodies[0].rows)
            .filter(row => row.cells.length > columnIndex)
            .map(row => row.cells[columnIndex].textContent.trim())
            .filter(value => value && value !== "--");
        const uniqueCompanies = [...new Set(companies)].sort((left, right) =>
            left.localeCompare(right, undefined, { numeric: true })
        );
        const selectedCompany = select.value;
        select.innerHTML = "<option value=\"\">All Companies</option>";
        uniqueCompanies.forEach(company => {
            const option = document.createElement("option");
            option.value = company;
            option.textContent = company;
            select.appendChild(option);
        });
        select.value = uniqueCompanies.includes(selectedCompany) ? selectedCompany : "";
    }

    function filterByCompany(table, company) {
        const makeHeader = Array.from(table.querySelectorAll("thead th")).find(header =>
            sortableLabels.has(header.textContent.trim().toLocaleLowerCase())
        );
        if (!makeHeader || !table.tBodies[0]) return;

        const columnIndex = makeHeader.cellIndex;
        Array.from(table.tBodies[0].rows).forEach(row => {
            const rowCompany = row.cells[columnIndex]?.textContent.trim() || "";
            row.hidden = Boolean(company && rowCompany !== company);
        });
    }

    function addCompanyControl(table, makeHeader) {
        const container = table.closest(".table-container") || table.parentElement;
        if (!container || container.querySelector("[data-company-sort-control]")) return;

        const control = document.createElement("label");
        control.className = "company-sort-control";
        control.dataset.companySortControl = "true";
        control.innerHTML = "<span>Company</span>";
        const select = document.createElement("select");
        select.setAttribute("aria-label", "Select company");
        select.addEventListener("change", () => filterByCompany(table, select.value));
        control.appendChild(select);
        container.insertBefore(control, table);
        updateCompanyOptions(table, select);
    }

    function initializeSortableTables() {
        document.querySelectorAll("table").forEach(table => {
            table.querySelectorAll("thead th").forEach(header => {
                const label = header.textContent.trim().toLocaleLowerCase();
                if (!sortableLabels.has(label) || header.dataset.sortable === "true") return;

                header.dataset.sortable = "true";
                header.title = "Sort by company";
                header.addEventListener("click", () => {
                    const direction = header.dataset.sortDirection === "ascending" ? -1 : 1;
                    sortTable(table, header, direction);
                });
                addCompanyControl(table, header);
            });

            const select = table.closest(".table-container")?.querySelector("[data-company-sort-control] select");
            if (select) {
                updateCompanyOptions(table, select);
                filterByCompany(table, select.value);
            }
        });
    }

    initializeSortableTables();

    // Only refresh controls when table contents change. Observing every DOM
    // change caused this observer to react to its own select-option updates,
    // repeatedly re-running forever and freezing pages with a Make column.
    const tableObserver = new MutationObserver(mutations => {
        const tableChanged = mutations.some(mutation =>
            mutation.target instanceof Element && Boolean(mutation.target.closest("table"))
        );
        if (tableChanged) initializeSortableTables();
    });
    tableObserver.observe(document.body, {
        childList: true,
        subtree: true
    });
})();
