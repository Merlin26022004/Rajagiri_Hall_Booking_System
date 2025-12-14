document.addEventListener("DOMContentLoaded", function () {
    const dateInput = document.getElementById("booking-date");
    if (!dateInput) return;

    const spaceSelect = document.querySelector("select[name='space_id']");

    async function loadUnavailableDates() {
        if (!spaceSelect) return;
        const spaceId = spaceSelect.value;
        if (!spaceId) return;

        // Example API call – adjust URL & response format to your backend
        const res = await fetch(`/api/unavailable-dates?space_id=${spaceId}`);
        if (!res.ok) return;

        const data = await res.json(); // e.g. ["2025-12-10","2025-12-11"]
        const unavailable = new Set(data);

        dateInput.addEventListener("input", () => {
            if (unavailable.has(dateInput.value)) {
                alert("This date is unavailable for the selected space.");
                dateInput.value = "";
            }
        });

        // Optional: you can also mark min date here
        const today = new Date().toISOString().split("T")[0];
        dateInput.min = today;
    }

    loadUnavailableDates();
    if (spaceSelect) {
        spaceSelect.addEventListener("change", loadUnavailableDates);
    }
});
