// Visual Query Builder - JavaScript Logic

// State management
const state = {
    catalog: null,
    tables: [],
    selectedTables: new Map(), // tableId -> {name, columns, position}
    selectedColumns: new Set(),
    joins: [],
    filters: [],
    sorts: [],
    limit: null,
    nextTableId: 0,
    draggedTable: null,
    draggedNode: null,
    dragOffset: { x: 0, y: 0 }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadCatalog();
    setupDragAndDrop();
    generateSQL();
});

// Load database catalog
async function loadCatalog() {
    try {
        showLoading();
        const response = await fetch('/api/v1/catalog');
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load catalog');
        }

        state.catalog = data;
        renderTableList(data.tables);
        hideLoading();
    } catch (error) {
        hideLoading();
        showAlert('Error loading database catalog: ' + error.message, 'danger');
    }
}

// Render table list in sidebar
function renderTableList(tables) {
    const tableList = document.getElementById('tableList');
    tableList.innerHTML = '';

    tables.forEach(table => {
        const li = document.createElement('li');
        li.className = 'table-item';
        li.draggable = true;
        li.dataset.tableName = table.name;

        const stats = table.statistics || {};
        const rowCount = stats.row_count ? stats.row_count.toLocaleString() : 'Unknown';

        li.innerHTML = `
            <div class="table-name">
                📋 ${table.name}
            </div>
            <div class="table-info">
                ${table.columns.length} columns · ${rowCount} rows
            </div>
        `;

        // Drag events
        li.addEventListener('dragstart', handleTableDragStart);
        li.addEventListener('dragend', handleTableDragEnd);

        tableList.appendChild(li);
    });
}

// Filter tables in sidebar
function filterTables(searchTerm) {
    const items = document.querySelectorAll('.table-item');
    const term = searchTerm.toLowerCase();

    items.forEach(item => {
        const tableName = item.dataset.tableName.toLowerCase();
        if (tableName.includes(term)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// Drag and drop setup
function setupDragAndDrop() {
    const canvasArea = document.getElementById('canvasArea');

    canvasArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        canvasArea.classList.add('drag-over');
    });

    canvasArea.addEventListener('dragleave', () => {
        canvasArea.classList.remove('drag-over');
    });

    canvasArea.addEventListener('drop', handleTableDrop);
}

// Handle table drag start
function handleTableDragStart(e) {
    state.draggedTable = e.target.dataset.tableName;
    e.target.classList.add('dragging');
}

// Handle table drag end
function handleTableDragEnd(e) {
    e.target.classList.remove('dragging');
    state.draggedTable = null;
}

// Handle table drop on canvas
function handleTableDrop(e) {
    e.preventDefault();
    const canvasArea = document.getElementById('canvasArea');
    canvasArea.classList.remove('drag-over');

    if (!state.draggedTable) return;

    // Get drop position relative to canvas
    const rect = canvasArea.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    addTableToCanvas(state.draggedTable, { x, y });
}

// Add table to canvas
function addTableToCanvas(tableName, position) {
    // Check if table already exists
    for (const [id, table] of state.selectedTables) {
        if (table.name === tableName) {
            showAlert(`Table "${tableName}" is already on the canvas`, 'warning');
            return;
        }
    }

    const table = state.catalog.tables.find(t => t.name === tableName);
    if (!table) return;

    const tableId = state.nextTableId++;

    state.selectedTables.set(tableId, {
        name: tableName,
        columns: table.columns,
        position: position
    });

    renderTableNode(tableId);

    // Remove empty message
    const emptyMsg = document.querySelector('.canvas-empty');
    if (emptyMsg) emptyMsg.remove();

    // Suggest joins if multiple tables
    if (state.selectedTables.size > 1) {
        suggestJoins();
    }

    generateSQL();
}

// Render table node on canvas
function renderTableNode(tableId) {
    const canvasArea = document.getElementById('canvasArea');
    const tableData = state.selectedTables.get(tableId);

    const node = document.createElement('div');
    node.className = 'table-node';
    node.id = `table-node-${tableId}`;
    node.style.left = tableData.position.x + 'px';
    node.style.top = tableData.position.y + 'px';

    const columnsHtml = tableData.columns.map((col, idx) => `
        <div class="column-item">
            <input type="checkbox" id="col-${tableId}-${idx}" onchange="handleColumnSelect(${tableId}, '${col.name}', this.checked)">
            <label for="col-${tableId}-${idx}" class="column-name">${col.name}</label>
            <span class="column-type">${col.data_type}</span>
        </div>
    `).join('');

    node.innerHTML = `
        <div class="table-node-header" onmousedown="startDragNode(event, ${tableId})">
            <span class="table-node-title">${tableData.name}</span>
            <button class="node-close" onclick="removeTable(${tableId})">×</button>
        </div>
        <div class="table-node-body">
            ${columnsHtml}
        </div>
    `;

    canvasArea.appendChild(node);
}

// Start dragging node
function startDragNode(e, tableId) {
    if (e.target.classList.contains('node-close')) return;

    state.draggedNode = tableId;
    const node = document.getElementById(`table-node-${tableId}`);
    const rect = node.getBoundingClientRect();

    state.dragOffset = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };

    document.addEventListener('mousemove', dragNode);
    document.addEventListener('mouseup', stopDragNode);
}

// Drag node
function dragNode(e) {
    if (state.draggedNode === null) return;

    const node = document.getElementById(`table-node-${state.draggedNode}`);
    const canvasArea = document.getElementById('canvasArea');
    const rect = canvasArea.getBoundingClientRect();

    const x = e.clientX - rect.left - state.dragOffset.x;
    const y = e.clientY - rect.top - state.dragOffset.y;

    node.style.left = Math.max(0, x) + 'px';
    node.style.top = Math.max(0, y) + 'px';

    // Update state
    const tableData = state.selectedTables.get(state.draggedNode);
    tableData.position = { x: Math.max(0, x), y: Math.max(0, y) };
}

// Stop dragging node
function stopDragNode() {
    state.draggedNode = null;
    document.removeEventListener('mousemove', dragNode);
    document.removeEventListener('mouseup', stopDragNode);
}

// Remove table from canvas
function removeTable(tableId) {
    state.selectedTables.delete(tableId);
    const node = document.getElementById(`table-node-${tableId}`);
    if (node) node.remove();

    // Remove related joins
    state.joins = state.joins.filter(j => !j.tables.includes(tableId));

    // Remove related filters
    state.filters = state.filters.filter(f => f.tableId !== tableId);

    // Show empty message if no tables
    if (state.selectedTables.size === 0) {
        const canvasArea = document.getElementById('canvasArea');
        canvasArea.innerHTML = '<div class="canvas-empty">Drag tables here to start building your query</div>';
    }

    generateSQL();
    renderJoins();
    renderFilters();
}

// Handle column selection
function handleColumnSelect(tableId, columnName, checked) {
    const tableData = state.selectedTables.get(tableId);
    const columnKey = `${tableData.name}.${columnName}`;

    if (checked) {
        state.selectedColumns.add(columnKey);
    } else {
        state.selectedColumns.delete(columnKey);
    }

    updateSelectedColumns();
    generateSQL();
}

// Update selected columns display
function updateSelectedColumns() {
    const container = document.getElementById('selectedColumns');

    if (state.selectedColumns.size === 0) {
        container.innerHTML = '<span style="color: #999;">No columns selected</span>';
        return;
    }

    container.innerHTML = Array.from(state.selectedColumns)
        .map(col => `<div style="padding: 4px; background: #e7f3ff; border-radius: 4px; margin: 2px 0;">${col}</div>`)
        .join('');
}

// Suggest joins based on foreign keys
async function suggestJoins() {
    if (!state.catalog.relationships || state.catalog.relationships.length === 0) return;

    const tableNames = Array.from(state.selectedTables.values()).map(t => t.name);

    // Find relationships between selected tables
    for (const rel of state.catalog.relationships) {
        if (tableNames.includes(rel.from_table) && tableNames.includes(rel.to_table)) {
            // Check if join already exists
            const exists = state.joins.some(j =>
                (j.leftTable === rel.from_table && j.rightTable === rel.to_table) ||
                (j.leftTable === rel.to_table && j.rightTable === rel.from_table)
            );

            if (!exists) {
                state.joins.push({
                    leftTable: rel.from_table,
                    leftColumn: rel.from_column,
                    rightTable: rel.to_table,
                    rightColumn: rel.to_column,
                    type: 'INNER'
                });
            }
        }
    }

    renderJoins();
    generateSQL();
}

// Add join
function addJoin() {
    const tables = Array.from(state.selectedTables.values());
    if (tables.length < 2) {
        showAlert('Add at least 2 tables to create a join', 'warning');
        return;
    }

    state.joins.push({
        leftTable: tables[0].name,
        leftColumn: tables[0].columns[0]?.name || 'id',
        rightTable: tables[1].name,
        rightColumn: tables[1].columns[0]?.name || 'id',
        type: 'INNER'
    });

    renderJoins();
    generateSQL();
}

// Render joins
function renderJoins() {
    const joinList = document.getElementById('joinList');
    joinList.innerHTML = '';

    if (state.joins.length === 0) {
        return;
    }

    state.joins.forEach((join, idx) => {
        const li = document.createElement('li');
        li.className = 'join-item';

        const tables = Array.from(state.selectedTables.values());
        const tableOptions = tables.map(t => `<option value="${t.name}" ${t.name === join.leftTable ? 'selected' : ''}>${t.name}</option>`).join('');

        li.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 8px;">${join.type} JOIN</div>
            <div class="join-controls">
                <select onchange="updateJoin(${idx}, 'leftTable', this.value)">${tableOptions}</select>
                <select onchange="updateJoin(${idx}, 'leftColumn', this.value)" id="leftCol-${idx}"></select>
            </div>
            <div class="join-controls">
                <select onchange="updateJoin(${idx}, 'rightTable', this.value)" id="rightTable-${idx}">${tableOptions}</select>
                <select onchange="updateJoin(${idx}, 'rightColumn', this.value)" id="rightCol-${idx}"></select>
            </div>
            <div class="join-controls">
                <select onchange="updateJoin(${idx}, 'type', this.value)">
                    <option value="INNER" ${join.type === 'INNER' ? 'selected' : ''}>INNER JOIN</option>
                    <option value="LEFT" ${join.type === 'LEFT' ? 'selected' : ''}>LEFT JOIN</option>
                    <option value="RIGHT" ${join.type === 'RIGHT' ? 'selected' : ''}>RIGHT JOIN</option>
                    <option value="FULL" ${join.type === 'FULL' ? 'selected' : ''}>FULL JOIN</option>
                </select>
                <button class="remove-btn" onclick="removeJoin(${idx})">Remove</button>
            </div>
        `;

        joinList.appendChild(li);

        // Populate column selects
        updateJoinColumnSelects(idx);
    });
}

// Update join column selects
function updateJoinColumnSelects(idx) {
    const join = state.joins[idx];

    const leftTable = Array.from(state.selectedTables.values()).find(t => t.name === join.leftTable);
    const rightTable = Array.from(state.selectedTables.values()).find(t => t.name === join.rightTable);

    if (leftTable) {
        const leftColSelect = document.getElementById(`leftCol-${idx}`);
        if (leftColSelect) {
            leftColSelect.innerHTML = leftTable.columns
                .map(c => `<option value="${c.name}" ${c.name === join.leftColumn ? 'selected' : ''}>${c.name}</option>`)
                .join('');
        }
    }

    if (rightTable) {
        const rightColSelect = document.getElementById(`rightCol-${idx}`);
        if (rightColSelect) {
            rightColSelect.innerHTML = rightTable.columns
                .map(c => `<option value="${c.name}" ${c.name === join.rightColumn ? 'selected' : ''}>${c.name}</option>`)
                .join('');
        }
    }
}

// Update join
function updateJoin(idx, field, value) {
    state.joins[idx][field] = value;

    if (field === 'leftTable' || field === 'rightTable') {
        updateJoinColumnSelects(idx);
    }

    generateSQL();
}

// Remove join
function removeJoin(idx) {
    state.joins.splice(idx, 1);
    renderJoins();
    generateSQL();
}

// Add filter
function addFilter() {
    const tables = Array.from(state.selectedTables.values());
    if (tables.length === 0) {
        showAlert('Add tables first', 'warning');
        return;
    }

    state.filters.push({
        table: tables[0].name,
        column: tables[0].columns[0]?.name || '',
        operator: '=',
        value: ''
    });

    renderFilters();
    generateSQL();
}

// Render filters
function renderFilters() {
    const filterList = document.getElementById('filterList');
    filterList.innerHTML = '';

    if (state.filters.length === 0) {
        return;
    }

    state.filters.forEach((filter, idx) => {
        const li = document.createElement('li');
        li.className = 'filter-item';

        const tables = Array.from(state.selectedTables.values());
        const tableOptions = tables.map(t => `<option value="${t.name}" ${t.name === filter.table ? 'selected' : ''}>${t.name}</option>`).join('');

        li.innerHTML = `
            <div class="filter-controls">
                <select onchange="updateFilter(${idx}, 'table', this.value)">${tableOptions}</select>
                <select onchange="updateFilter(${idx}, 'column', this.value)" id="filterCol-${idx}"></select>
            </div>
            <div class="filter-controls">
                <select onchange="updateFilter(${idx}, 'operator', this.value)">
                    <option value="=" ${filter.operator === '=' ? 'selected' : ''}>=</option>
                    <option value="!=" ${filter.operator === '!=' ? 'selected' : ''}>!=</option>
                    <option value=">" ${filter.operator === '>' ? 'selected' : ''}>&gt;</option>
                    <option value="<" ${filter.operator === '<' ? 'selected' : ''}>&lt;</option>
                    <option value=">=" ${filter.operator === '>=' ? 'selected' : ''}>&gt;=</option>
                    <option value="<=" ${filter.operator === '<=' ? 'selected' : ''}>&lt;=</option>
                    <option value="LIKE" ${filter.operator === 'LIKE' ? 'selected' : ''}>LIKE</option>
                    <option value="IN" ${filter.operator === 'IN' ? 'selected' : ''}>IN</option>
                </select>
                <input type="text" value="${filter.value}" onchange="updateFilter(${idx}, 'value', this.value)" placeholder="value">
            </div>
            <button class="remove-btn" onclick="removeFilter(${idx})">Remove</button>
        `;

        filterList.appendChild(li);

        // Populate column select
        updateFilterColumnSelect(idx);
    });
}

// Update filter column select
function updateFilterColumnSelect(idx) {
    const filter = state.filters[idx];
    const table = Array.from(state.selectedTables.values()).find(t => t.name === filter.table);

    if (table) {
        const colSelect = document.getElementById(`filterCol-${idx}`);
        if (colSelect) {
            colSelect.innerHTML = table.columns
                .map(c => `<option value="${c.name}" ${c.name === filter.column ? 'selected' : ''}>${c.name}</option>`)
                .join('');
        }
    }
}

// Update filter
function updateFilter(idx, field, value) {
    state.filters[idx][field] = value;

    if (field === 'table') {
        updateFilterColumnSelect(idx);
    }

    generateSQL();
}

// Remove filter
function removeFilter(idx) {
    state.filters.splice(idx, 1);
    renderFilters();
    generateSQL();
}

// Add sort
function addSort() {
    const tables = Array.from(state.selectedTables.values());
    if (tables.length === 0) {
        showAlert('Add tables first', 'warning');
        return;
    }

    state.sorts.push({
        table: tables[0].name,
        column: tables[0].columns[0]?.name || '',
        direction: 'ASC'
    });

    renderSorts();
    generateSQL();
}

// Render sorts
function renderSorts() {
    const sortList = document.getElementById('sortList');
    sortList.innerHTML = '';

    if (state.sorts.length === 0) {
        return;
    }

    state.sorts.forEach((sort, idx) => {
        const li = document.createElement('li');
        li.className = 'sort-item';

        const tables = Array.from(state.selectedTables.values());
        const tableOptions = tables.map(t => `<option value="${t.name}" ${t.name === sort.table ? 'selected' : ''}>${t.name}</option>`).join('');

        li.innerHTML = `
            <div class="sort-controls">
                <select onchange="updateSort(${idx}, 'table', this.value)">${tableOptions}</select>
                <select onchange="updateSort(${idx}, 'column', this.value)" id="sortCol-${idx}"></select>
                <select onchange="updateSort(${idx}, 'direction', this.value)">
                    <option value="ASC" ${sort.direction === 'ASC' ? 'selected' : ''}>ASC</option>
                    <option value="DESC" ${sort.direction === 'DESC' ? 'selected' : ''}>DESC</option>
                </select>
                <button class="remove-btn" onclick="removeSort(${idx})">Remove</button>
            </div>
        `;

        sortList.appendChild(li);

        // Populate column select
        updateSortColumnSelect(idx);
    });
}

// Update sort column select
function updateSortColumnSelect(idx) {
    const sort = state.sorts[idx];
    const table = Array.from(state.selectedTables.values()).find(t => t.name === sort.table);

    if (table) {
        const colSelect = document.getElementById(`sortCol-${idx}`);
        if (colSelect) {
            colSelect.innerHTML = table.columns
                .map(c => `<option value="${c.name}" ${c.name === sort.column ? 'selected' : ''}>${c.name}</option>`)
                .join('');
        }
    }
}

// Update sort
function updateSort(idx, field, value) {
    state.sorts[idx][field] = value;

    if (field === 'table') {
        updateSortColumnSelect(idx);
    }

    generateSQL();
}

// Remove sort
function removeSort(idx) {
    state.sorts.splice(idx, 1);
    renderSorts();
    generateSQL();
}

// Generate SQL from visual representation
function generateSQL() {
    if (state.selectedTables.size === 0) {
        document.getElementById('sqlOutput').textContent = '-- Add tables to generate SQL';
        return;
    }

    let sql = '';

    // SELECT clause
    if (state.selectedColumns.size > 0) {
        sql += 'SELECT\n  ' + Array.from(state.selectedColumns).join(',\n  ');
    } else {
        sql += 'SELECT *';
    }

    // FROM clause
    const tables = Array.from(state.selectedTables.values());
    sql += `\nFROM ${tables[0].name}`;

    // JOIN clauses
    state.joins.forEach(join => {
        sql += `\n${join.type} JOIN ${join.rightTable}`;
        sql += `\n  ON ${join.leftTable}.${join.leftColumn} = ${join.rightTable}.${join.rightColumn}`;
    });

    // WHERE clause
    if (state.filters.length > 0) {
        sql += '\nWHERE ';
        sql += state.filters.map(f => {
            let value = f.value;
            if (f.operator !== 'IN') {
                value = isNaN(value) ? `'${value}'` : value;
            }
            return `${f.table}.${f.column} ${f.operator} ${value}`;
        }).join('\n  AND ');
    }

    // ORDER BY clause
    if (state.sorts.length > 0) {
        sql += '\nORDER BY ';
        sql += state.sorts.map(s => `${s.table}.${s.column} ${s.direction}`).join(', ');
    }

    // LIMIT clause
    const limit = document.getElementById('limitInput').value;
    if (limit) {
        sql += `\nLIMIT ${limit}`;
    }

    sql += ';';

    document.getElementById('sqlOutput').textContent = sql;
}

// Copy SQL to clipboard
function copySQL() {
    const sql = document.getElementById('sqlOutput').textContent;
    navigator.clipboard.writeText(sql).then(() => {
        showAlert('SQL copied to clipboard!', 'success');
    });
}

// Validate SQL
async function validateSQL() {
    const sql = document.getElementById('sqlOutput').textContent;

    try {
        showLoading();
        const response = await fetch('/api/v1/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sql: sql })
        });

        const data = await response.json();
        hideLoading();

        const resultsDiv = document.getElementById('validationResults');
        let html = '';

        if (data.valid) {
            html += '<div class="alert alert-success">✓ Query is valid</div>';
        } else {
            html += '<div class="alert alert-danger">✗ Query has errors</div>';
        }

        if (data.errors && data.errors.length > 0) {
            html += '<div class="alert alert-danger"><strong>Errors:</strong><ul>';
            data.errors.forEach(err => html += `<li>${err}</li>`);
            html += '</ul></div>';
        }

        if (data.warnings && data.warnings.length > 0) {
            html += '<div class="alert alert-warning"><strong>Warnings:</strong><ul>';
            data.warnings.forEach(warn => html += `<li>${warn}</li>`);
            html += '</ul></div>';
        }

        if (data.suggestions && data.suggestions.length > 0) {
            html += '<div class="alert alert-warning"><strong>Suggestions:</strong><ul>';
            data.suggestions.forEach(sug => html += `<li>${sug}</li>`);
            html += '</ul></div>';
        }

        resultsDiv.innerHTML = html;

    } catch (error) {
        hideLoading();
        showAlert('Validation failed: ' + error.message, 'danger');
    }
}

// Execute query
async function executeQuery() {
    const sql = document.getElementById('sqlOutput').textContent;

    if (confirm('Execute this query?\n\n' + sql)) {
        // Redirect to main UI with the query
        window.location.href = `/?sql=${encodeURIComponent(sql)}`;
    }
}

// Save query
function saveQuery() {
    const sql = document.getElementById('sqlOutput').textContent;
    const name = prompt('Enter a name for this query:');

    if (name) {
        localStorage.setItem(`query_${Date.now()}`, JSON.stringify({
            name: name,
            sql: sql,
            state: {
                tables: Array.from(state.selectedTables.entries()),
                columns: Array.from(state.selectedColumns),
                joins: state.joins,
                filters: state.filters,
                sorts: state.sorts
            },
            created: new Date().toISOString()
        }));

        showAlert('Query saved!', 'success');
    }
}

// Load history
function loadHistory() {
    const keys = Object.keys(localStorage).filter(k => k.startsWith('query_'));

    if (keys.length === 0) {
        showAlert('No saved queries', 'warning');
        return;
    }

    // Simple history display
    const queries = keys.map(k => JSON.parse(localStorage.getItem(k)));
    const html = queries.map((q, i) => `
        <div style="padding: 10px; margin: 5px 0; background: #f0f0f0; border-radius: 4px; cursor: pointer;" onclick="loadSavedQuery('${keys[i]}')">
            <strong>${q.name}</strong><br>
            <small>${new Date(q.created).toLocaleString()}</small>
        </div>
    `).join('');

    const container = document.createElement('div');
    container.innerHTML = `<div style="max-height: 400px; overflow-y: auto;">${html}</div>`;
    container.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.2); z-index: 10000; max-width: 500px;';

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 9999;';
    overlay.onclick = () => {
        document.body.removeChild(overlay);
        document.body.removeChild(container);
    };

    document.body.appendChild(overlay);
    document.body.appendChild(container);
}

// Load saved query
function loadSavedQuery(key) {
    // Implementation for loading saved query state
    const saved = JSON.parse(localStorage.getItem(key));
    showAlert('Query loaded: ' + saved.name, 'success');
    // TODO: Restore state
}

// Helper functions
function showLoading() {
    document.getElementById('loading').classList.add('show');
}

function hideLoading() {
    document.getElementById('loading').classList.remove('show');
}

function showAlert(message, type) {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.cssText = 'position: fixed; top: 80px; right: 20px; z-index: 10000; min-width: 300px; animation: slideIn 0.3s;';

    document.body.appendChild(alert);

    setTimeout(() => {
        alert.style.animation = 'slideOut 0.3s';
        setTimeout(() => document.body.removeChild(alert), 300);
    }, 3000);
}
