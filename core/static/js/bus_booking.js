document.addEventListener('DOMContentLoaded', function() {
    
    // === 1. BEAUTIFUL CALENDAR ===
    flatpickr("#journeyDate", {
        minDate: "today",
        dateFormat: "Y-m-d",
        disableMobile: "true"
    });

    // === 2. SMART BUS LOGIC (Block if too many students) ===
    const headcountInput = document.getElementById('headcountInput');
    const busSelect = document.getElementById('busSelect');
    const options = busSelect.querySelectorAll('option');
    const suggestionText = document.getElementById('busSuggestionText');
    const submitBtn = document.getElementById('submitBtn');

    if (headcountInput) {
        headcountInput.addEventListener('input', function() {
            const count = parseInt(this.value) || 0;
            let validBusFound = false;
            let bestFit = null;
            let minWaste = Infinity;

            suggestionText.style.display = 'none';
            suggestionText.className = "form-text fw-bold mt-2"; // Reset classes

            options.forEach(opt => {
                if (opt.value === "") return;

                const cap = parseInt(opt.getAttribute('data-capacity'));
                
                if (count > cap) {
                    // Disable small buses
                    opt.disabled = true;
                    opt.textContent = `❌ ${opt.getAttribute('data-name')} (Cap: ${cap}) - Too Small`;
                } else {
                    // Enable valid buses
                    opt.disabled = false;
                    opt.textContent = `${opt.getAttribute('data-name')} (Capacity: ${cap})`;
                    validBusFound = true;

                    // Find best fit
                    const waste = cap - count;
                    if (waste < minWaste) {
                        minWaste = waste;
                        bestFit = opt;
                    }
                }
            });

            // LOGIC: Block submission if no bus fits
            if (count > 0 && !validBusFound) {
                busSelect.value = "";
                submitBtn.disabled = true; // BLOCK THE BOOKING
                submitBtn.textContent = "Cannot Book: Too many passengers";
                submitBtn.classList.add("btn-secondary");
                submitBtn.classList.remove("btn-google");
                
                suggestionText.style.display = 'block';
                suggestionText.classList.add("text-danger");
                suggestionText.innerHTML = `<i class="bi bi-x-circle-fill"></i> No single vehicle can hold ${count} people. Please contact Transport Officer directly.`;
            } else if (bestFit) {
                // Auto-select and Allow
                busSelect.value = bestFit.value;
                submitBtn.disabled = false;
                submitBtn.textContent = "Submit Request";
                submitBtn.classList.remove("btn-secondary");
                submitBtn.classList.add("btn-google");

                suggestionText.style.display = 'block';
                suggestionText.classList.add("text-success");
                suggestionText.innerHTML = `<i class="bi bi-stars"></i> Auto-selected <strong>${bestFit.getAttribute('data-name')}</strong> for ${count} passengers.`;
            }
        });
    }

    // === 3. TIME VALIDATION ===
    const startTime = document.getElementById('startTime');
    const endTime = document.getElementById('endTime');

    function validateTime() {
        if (startTime.value && endTime.value) {
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