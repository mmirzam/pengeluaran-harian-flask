// --- Fungsi Format Nominal untuk Input Form ---
function formatNominal(input) {
    let value = input.value.replace(/\D/g, ''); 
    let hiddenInputId;
    if (input.id.includes('nominal')) {
        hiddenInputId = 'nominal_clean';
    } else if (input.id.includes('modal')) {
        hiddenInputId = 'modal_clean';
    } else if (input.id.includes('jual')) {
        hiddenInputId = 'jual_clean';
    }

    const hiddenInput = document.getElementById(hiddenInputId);
    const min = parseInt(hiddenInput.min) || 0;
    const max = parseInt(hiddenInput.max) || 200000;

    let numericValue = parseInt(value) || 0;
    if (numericValue > max && hiddenInputId === 'nominal_clean') {
        value = String(max);
        numericValue = max;
    } 

    let formattedValue = '';
    if (value.length > 0) {
        formattedValue = numericValue.toLocaleString('id-ID');
    }
    input.value = formattedValue;
    hiddenInput.value = numericValue;
}

// --- Validasi Form Pengeluaran ---
if (document.getElementById('expenseForm')) {
    document.getElementById('expenseForm').addEventListener('submit', function(event) {
        const nominalCleanInput = document.getElementById('nominal_clean');
        const nominalValue = parseInt(nominalCleanInput.value) || 0;
        const min = parseInt(nominalCleanInput.min);
        const max = parseInt(nominalCleanInput.max);

        if (nominalValue < min || nominalValue > max) {
            event.preventDefault();
            alert(`Nominal Pengeluaran harus antara ${min.toLocaleString('id-ID')} dan ${max.toLocaleString('id-ID')}.`);
        }
    });
}

// --- Validasi Form Pemasukan ---
if (document.getElementById('incomeForm')) {
    document.getElementById('incomeForm').addEventListener('submit', function(event) {
        const modalCleanInput = document.getElementById('modal_clean');
        const jualCleanInput = document.getElementById('jual_clean');
        const modalValue = parseInt(modalCleanInput.value) || 0;
        const jualValue = parseInt(jualCleanInput.value) || 0;
        const min = parseInt(modalCleanInput.min);

        if (modalValue < min || jualValue < min) {
            event.preventDefault();
            alert(`Nominal Modal dan Jual minimal harus ${min.toLocaleString('id-ID')}.`);
        }
    });
}

// --- Chart Initialization ---
function initializeCharts() {
    // Data dari Flask
    const weeklyLabelsExp = window.weeklyLabelsExp || [];
    const weeklyDataExp = window.weeklyDataExp || [];
    const monthlyLabelsExp = window.monthlyLabelsExp || [];
    const monthlyDataExp = window.monthlyDataExp || [];

    const weeklyLabelsInc = window.weeklyLabelsInc || [];
    const weeklyDataInc = window.weeklyDataInc || [];
    const monthlyLabelsInc = window.monthlyLabelsInc || [];
    const monthlyDataInc = window.monthlyDataInc || [];

    // --- Chart Pengeluaran Mingguan ---
    if (document.getElementById('weeklyChartExp')) {
        new Chart(document.getElementById('weeklyChartExp'), {
            type: 'bar',
            data: {
                labels: weeklyLabelsExp,
                datasets: [{
                    data: weeklyDataExp,
                    backgroundColor: 'rgba(255,99,132,0.6)'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    datalabels: {
                        anchor: 'end',
                        align: 'top',
                        formatter: (value) => value.toLocaleString('id-ID'),
                        font: { weight: 'bold', size: 11 }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Nominal' } },
                    x: { title: { display: true, text: 'Hari' } }
                }
            },
            plugins: [ChartDataLabels]
        });
    }

    // --- Chart Pengeluaran Bulanan ---
    if (document.getElementById('monthlyChartExp')) {
        new Chart(document.getElementById('monthlyChartExp'), {
            type: 'line',
            data: {
                labels: monthlyLabelsExp,
                datasets: [{
                    data: monthlyDataExp,
                    backgroundColor: 'rgba(54,162,235,0.6)',
                    borderColor: 'rgba(54,162,235,1)',
                    fill: false,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    datalabels: {
                        align: 'top',
                        anchor: 'end',
                        formatter: (value) => value.toLocaleString('id-ID'),
                        font: { weight: 'bold', size: 11 }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Nominal' } },
                    x: { title: { display: true, text: 'Bulan' } }
                }
            },
            plugins: [ChartDataLabels]
        });
    }

    // --- Chart Pemasukan Mingguan ---
    if (document.getElementById('weeklyChartInc')) {
        new Chart(document.getElementById('weeklyChartInc'), {
            type: 'bar',
            data: {
                labels: weeklyLabelsInc,
                datasets: [{
                    data: weeklyDataInc,
                    backgroundColor: 'rgba(75,192,192,0.6)'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    datalabels: {
                        anchor: 'end',
                        align: 'top',
                        formatter: (value) => value.toLocaleString('id-ID'),
                        font: { weight: 'bold', size: 11 }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Nominal' } },
                    x: { title: { display: true, text: 'Hari' } }
                }
            },
            plugins: [ChartDataLabels]
        });
    }

    // --- Chart Pemasukan Bulanan ---
    if (document.getElementById('monthlyChartInc')) {
        new Chart(document.getElementById('monthlyChartInc'), {
            type: 'line',
            data: {
                labels: monthlyLabelsInc,
                datasets: [{
                    data: monthlyDataInc,
                    backgroundColor: 'rgba(153,102,255,0.6)',
                    borderColor: 'rgba(153,102,255,1)',
                    fill: false,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    datalabels: {
                        align: 'top',
                        anchor: 'end',
                        formatter: (value) => value.toLocaleString('id-ID'),
                        font: { weight: 'bold', size: 11 }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Nominal' } },
                    x: { title: { display: true, text: 'Bulan' } }
                }
            },
            plugins: [ChartDataLabels]
        });
    }
}

document.addEventListener('DOMContentLoaded', initializeCharts);
