document.addEventListener("DOMContentLoaded", function() {
    const dateInput = document.getElementById("dateInput");
    const spaceSelect = document.getElementById("spaceSelect");
    const slotsBox = document.getElementById("existingSlots");
    const facilitiesContainer = document.getElementById("facilitiesContainer");

    // === NEW: PRIORITY LOGIC ELEMENTS ===
    const resourceType = document.getElementById('resourceType');
    const externalFields = document.getElementById('externalFields');
    const resourceName = document.getElementById('resourceName');
    const resourceNumber = document.getElementById('resourceNumber');

    // === 1. DISABLE PAST DATES ===
    if (dateInput) {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        dateInput.min = `${yyyy}-${mm}-${dd}`;
    }

    // === 2. EVENT LISTENERS ===
    if (spaceSelect && dateInput) {
        // When Space Changes: Load Facilities, Blocked Dates, and Slots
        spaceSelect.addEventListener("change", function() {
            loadFacilities();
            checkUnavailableDates();
            loadSlots();
        });

        // When Date Changes: Check validity and Load Slots
        dateInput.addEventListener("change", function() {
            checkUnavailableDates().then(isValid => {
                if (isValid) loadSlots();
            });
        });

        // === 3. AUTO-TRIGGER ON LOAD ===
        if (spaceSelect.value) {
            loadFacilities();
            checkUnavailableDates();
            if (dateInput.value) {
                loadSlots();
            }
        }
    }

    // === NEW: PRIORITY TOGGLE LISTENER ===
    if (resourceType) {
        // Run once on load (in case browser cached the selection)
        toggleExternalFields();

        // Run on change
        resourceType.addEventListener('change', toggleExternalFields);
    }

    // === FUNCTION: Toggle External Fields ===
    function toggleExternalFields() {
        if (!resourceType || !externalFields) return;

        if (resourceType.value === 'External') {
            externalFields.classList.remove('d-none');
            if(resourceName) resourceName.setAttribute('required', 'required');
            if(resourceNumber) resourceNumber.setAttribute('required', 'required');
        } else {
            externalFields.classList.add('d-none');
            if(resourceName) {
                resourceName.removeAttribute('required');
                resourceName.value = ''; // Clear value
            }
            if(resourceNumber) {
                resourceNumber.removeAttribute('required');
                resourceNumber.value = ''; // Clear value
            }
        }
    }

    // === 4. CHECK UNAVAILABLE DATES ===
    async function checkUnavailableDates() {
        if (!spaceSelect.value) return true;

        try {
            const res = await fetch(`/api/unavailable-dates/?space_id=${spaceSelect.value}`);
            if (!res.ok) return true;

            const data = await res.json(); 
            const unavailable = new Set(data); 
            const selectedDate = dateInput.value;

            if (selectedDate && unavailable.has(selectedDate)) {
                alert("This date is completely blocked for the selected space.");
                dateInput.value = ""; 
                if(slotsBox) slotsBox.classList.add("d-none");
                return false;
            }
            return true;
        } catch (err) {
            console.error("Error checking blocked dates:", err);
            return true;
        }
    }

    // === 5. LOAD TIME SLOTS ===
    function loadSlots(){
        const space = spaceSelect.value;
        const date = dateInput.value;
        
        if(!space || !date) {
            if(slotsBox) slotsBox.classList.add("d-none");
            return;
        }

        fetch(`/api/space-day-slots/?space_id=${space}&date=${date}`)
        .then(r => r.json())
        .then(data => {
            if (!slotsBox) return;

            if(data.length === 0){
                slotsBox.classList.add("d-none");
                return;
            }

            slotsBox.classList.remove("d-none");
            // Use flex-wrap badges for a cleaner look than a raw list
            const slotsHtml = data.map(t => 
                `<span class="badge bg-danger me-1 mb-1">❌ ${t.start} – ${t.end}</span>`
            ).join(" ");
            
            slotsBox.innerHTML = `<div class="small text-muted mb-1">Already booked:</div>${slotsHtml}`;
        })
        .catch(err => console.error("Error loading slots:", err));
    }

    // === 6. LOAD FACILITIES ===
    function loadFacilities() {
        const spaceId = spaceSelect.value;
        
        if (!facilitiesContainer) return;

        if (!spaceId) {
            facilitiesContainer.innerHTML = '<p class="text-muted small mb-0 fst-italic">Select a space to see available equipment.</p>';
            return;
        }

        fetch(`/api/space-facilities/?space_id=${spaceId}`)
        .then(response => response.json())
        .then(data => {
            if (data.length === 0) {
                facilitiesContainer.innerHTML = '<p class="text-muted small mb-0">No specific facilities listed for this hall.</p>';
                return;
            }

            let html = "";
            data.forEach(fac => {
                html += `
                <div class="col-md-4 col-sm-6 mb-2">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" 
                               name="facilities" 
                               value="${fac.id}" 
                               id="fac_${fac.id}">
                        <label class="form-check-label" for="fac_${fac.id}">
                            ${fac.name}
                        </label>
                    </div>
                </div>`;
            });
            facilitiesContainer.innerHTML = html;
        })
        .catch(err => console.error("Error loading facilities:", err));
    }
});