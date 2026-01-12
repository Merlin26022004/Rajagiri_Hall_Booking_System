document.addEventListener('DOMContentLoaded', function() {
    
    const countInput = document.getElementById('studentCount');
    if (countInput) {
        const spaceSelect = document.getElementById('spaceSelect');
        const options = spaceSelect.querySelectorAll('option');
        const recommendText = document.getElementById('recommendationText');

        countInput.addEventListener('input', function() {
            const requiredSeats = parseInt(this.value) || 0;
            let bestFitOption = null;
            let smallestDifference = Infinity;

            recommendText.style.display = 'none';

            options.forEach(opt => {
                if (opt.value === "") return;

                const capacity = parseInt(opt.getAttribute('data-capacity'));
                const name = opt.getAttribute('data-name');

                if (capacity < requiredSeats) {
                    opt.disabled = true;
                    opt.textContent = `❌ ${name} (Cap: ${capacity}) - Too Small`;
                } else {
                    opt.disabled = false;
                    opt.textContent = `${name} (Capacity: ${capacity})`;

                    const diff = capacity - requiredSeats;
                    if (diff < smallestDifference) {
                        smallestDifference = diff;
                        bestFitOption = opt;
                    }
                }
            });

            if (bestFitOption) {
                spaceSelect.value = bestFitOption.value;
                recommendText.style.display = 'block';
                recommendText.innerHTML = `<i class="bi bi-stars me-1"></i> Auto-selected <strong>${bestFitOption.getAttribute('data-name')}</strong> as the best fit!`;
            } else if (requiredSeats > 0) {
                spaceSelect.value = "";
                recommendText.style.display = 'block';
                recommendText.className = "form-text text-danger fw-bold mt-2";
                recommendText.innerHTML = `<i class="bi bi-exclamation-circle me-1"></i> No single room can hold ${requiredSeats} students.`;
            }
        });
    }

    const toggle = document.getElementById('customTimeToggle');
    if (toggle) {
        toggle.addEventListener('change', function() {
            const standardInputs = document.querySelectorAll('.standard-time');
            const customInputs = document.querySelectorAll('.custom-time');
            
            if (this.checked) {
                standardInputs.forEach(el => el.classList.add('d-none'));
                customInputs.forEach(el => el.classList.remove('d-none'));
                document.querySelector('[name="start_time_custom"]').required = true;
                document.querySelector('[name="end_time_custom"]').required = true;
                document.querySelector('[name="start_time_select"]').required = false;
                document.querySelector('[name="end_time_select"]').required = false;
            } else {
                standardInputs.forEach(el => el.classList.remove('d-none'));
                customInputs.forEach(el => el.classList.add('d-none'));
                document.querySelector('[name="start_time_custom"]').required = false;
                document.querySelector('[name="end_time_custom"]').required = false;
                document.querySelector('[name="start_time_select"]').required = true;
                document.querySelector('[name="end_time_select"]').required = true;
            }
        });
    }

    const endPicker = flatpickr("#endDate", {
        minDate: "today",
        dateFormat: "Y-m-d",
        disableMobile: "true"
    });

    flatpickr("#startDate", {
        minDate: "today",
        dateFormat: "Y-m-d",
        disableMobile: "true",
        onChange: function(selectedDates, dateStr, instance) {
            endPicker.set('minDate', dateStr);
        }
    });
});