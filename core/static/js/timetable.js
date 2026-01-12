document.addEventListener('DOMContentLoaded', function() {
    // === 1. SMART CAPACITY LOGIC ===
    // Check if 'studentCount' exists to avoid errors on other pages
    const countInput = document.getElementById('studentCount');
    
    if (countInput) {
        const spaceSelect = document.getElementById('spaceSelect');
        const options = spaceSelect.querySelectorAll('option');
        const recommendText = document.getElementById('recommendationText');

        countInput.addEventListener('input', function() {
            const requiredSeats = parseInt(this.value) || 0;
            let bestFitOption = null;
            let smallestDifference = Infinity;

            // Reset text
            recommendText.style.display = 'none';

            options.forEach(opt => {
                if (opt.value === "") return; // Skip placeholder

                const capacity = parseInt(opt.getAttribute('data-capacity'));
                const name = opt.getAttribute('data-name');

                if (capacity < requiredSeats) {
                    // Room is too small: Disable it
                    opt.disabled = true;
                    opt.textContent = `❌ ${name} (Cap: ${capacity}) - Too Small`;
                } else {
                    // Room fits: Enable it
                    opt.disabled = false;
                    opt.textContent = `${name} (Capacity: ${capacity})`;

                    // Find "Best Fit" (Smallest room that fits the group)
                    const diff = capacity - requiredSeats;
                    if (diff < smallestDifference) {
                        smallestDifference = diff;
                        bestFitOption = opt;
                    }
                }
            });

            // Auto-Select the Best Fit
            if (bestFitOption) {
                spaceSelect.value = bestFitOption.value;
                recommendText.style.display = 'block';
                recommendText.innerHTML = `<i class="bi bi-stars me-1"></i> Auto-selected <strong>${bestFitOption.getAttribute('data-name')}</strong> as the best fit!`;
            } else if (requiredSeats > 0) {
                // No room found
                spaceSelect.value = "";
                recommendText.style.display = 'block';
                recommendText.className = "form-text text-danger fw-bold mt-2";
                recommendText.innerHTML = `<i class="bi bi-exclamation-circle me-1"></i> No single room can hold ${requiredSeats} students.`;
            }
        });
    }

    // === 2. TIME TOGGLE LOGIC ===
    const toggle = document.getElementById('customTimeToggle');
    if (toggle) {
        toggle.addEventListener('change', function() {
            const standardInputs = document.querySelectorAll('.standard-time');
            const customInputs = document.querySelectorAll('.custom-time');
            
            if (this.checked) {
                // Show Custom, Hide Standard
                standardInputs.forEach(el => el.classList.add('d-none'));
                customInputs.forEach(el => el.classList.remove('d-none'));
                
                // Update 'Required' attributes
                document.querySelector('[name="start_time_custom"]').required = true;
                document.querySelector('[name="end_time_custom"]').required = true;
                document.querySelector('[name="start_time_select"]').required = false;
                document.querySelector('[name="end_time_select"]').required = false;
            } else {
                // Show Standard, Hide Custom
                standardInputs.forEach(el => el.classList.remove('d-none'));
                customInputs.forEach(el => el.classList.add('d-none'));
                
                // Update 'Required' attributes
                document.querySelector('[name="start_time_custom"]').required = false;
                document.querySelector('[name="end_time_custom"]').required = false;
                document.querySelector('[name="start_time_select"]').required = true;
                document.querySelector('[name="end_time_select"]').required = true;
            }
        });
    }

    // === 3. PREVENT PAST DATES ===
    const startDate = document.getElementById('startDate');
    if (startDate) {
        const today = new Date().toISOString().split('T')[0];
        
        // Block past dates for Start Date
        startDate.setAttribute('min', today);
        document.getElementById('endDate').setAttribute('min', today);
        
        // Ensure End Date cannot be before Start Date
        startDate.addEventListener('change', function() {
            document.getElementById('endDate').setAttribute('min', this.value);
        });
    }
});