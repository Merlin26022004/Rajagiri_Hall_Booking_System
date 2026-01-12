document.addEventListener('DOMContentLoaded', function() {
    
    // === 1. BLOCK PAST DATES (Local System Time Fix) ===
    const dateInput = document.getElementById('journeyDate');
    if (dateInput) {
        const now = new Date();
        
        // Manually build YYYY-MM-DD to respect local timezone (IST)
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
        const day = String(now.getDate()).padStart(2, '0');
        
        const todayLocal = `${year}-${month}-${day}`;
        dateInput.setAttribute('min', todayLocal);
    }

    // === 2. TIME VALIDATION (End Time > Start Time) ===
    const startTime = document.getElementById('startTime');
    const endTime = document.getElementById('endTime');

    function validateTime() {
        if (startTime.value && endTime.value) {
            // Simple string comparison works for 24h format (e.g. "14:00" > "09:00")
            if (endTime.value <= startTime.value) {
                endTime.setCustomValidity("Return time must be after departure time.");
            } else {
                endTime.setCustomValidity("");
            }
        }
    }

    if (startTime && endTime) {
        startTime.addEventListener('change', validateTime);
        endTime.addEventListener('change', validateTime);
    }
});