document.addEventListener('DOMContentLoaded', function() {
    const chartCanvas = document.getElementById('popularityChart');
    if (!chartCanvas) return; // Exit if chart element doesn't exist

    const ctx = chartCanvas.getContext('2d');
    
    // Parse the data from the hidden JSON script tag
    const dataElement = document.getElementById('chart-data');
    if (!dataElement) return;

    const chartData = JSON.parse(dataElement.textContent);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Approved Bookings',
                data: chartData.data,
                backgroundColor: '#0d6efd',
                hoverBackgroundColor: '#0b5ed7',
                borderRadius: 6,
                maxBarThickness: 60, 
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#333',
                    padding: 10,
                    cornerRadius: 4,
                    displayColors: false,
                    callbacks: {
                        label: (ctx) => ctx.raw + (ctx.raw === 1 ? ' Booking' : ' Bookings')
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    border: { display: false },
                    grid: { color: '#f0f0f0' },
                    ticks: { stepSize: 1, color: '#999' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#555', font: { weight: 'bold' } }
                }
            },
            layout: {
                padding: { top: 10 }
            }
        }
    });
});