document.addEventListener('DOMContentLoaded', () => {
    // Calculate min and max dates dynamically (e.g., today - 1 days to today + 3 days)
    const today = new Date();
    const minDateObj = new Date(today);
    minDateObj.setDate(today.getDate() - 3);
    const maxDateObj = new Date(today);
    maxDateObj.setDate(today.getDate() + 3);

    const minDate = minDateObj.toISOString().split('T')[0];
    const maxDate = maxDateObj.toISOString().split('T')[0];

    const adjustDate = (inputId, prevButtonId, nextButtonId, minDate, maxDate) => {
        const input = document.getElementById(inputId);
        const prevButton = document.getElementById(prevButtonId);
        const nextButton = document.getElementById(nextButtonId);

        // Set the min and max attributes for the date input
        input.setAttribute('min', minDate);
        input.setAttribute('max', maxDate);

        // Set the current date as the default value
        const today = new Date();
        const formattedToday = today.toISOString().split('T')[0];
        input.value = formattedToday >= minDate && formattedToday <= maxDate ? formattedToday : minDate;

        const updateButtonState = () => {
            const currentDate = new Date(input.value);
            prevButton.disabled = currentDate <= new Date(minDate);
            nextButton.disabled = currentDate >= new Date(maxDate);

            prevButton.classList.toggle('disabled:bg-gray-200', prevButton.disabled);
            prevButton.classList.toggle('disabled:text-gray-400', prevButton.disabled);
            nextButton.classList.toggle('disabled:bg-gray-200', nextButton.disabled);
            nextButton.classList.toggle('disabled:text-gray-400', nextButton.disabled);
        };

        const incrementDate = (days) => {
            const currentDate = new Date(input.value);
            currentDate.setDate(currentDate.getDate() + days);
            input.value = currentDate.toISOString().split('T')[0];
            updateButtonState();
        };

        prevButton.addEventListener('click', (event) => {
            event.preventDefault();
            incrementDate(-1);
        });
        nextButton.addEventListener('click', (event) => {
            event.preventDefault();
            incrementDate(1);
        });

        // Initialize button states
        updateButtonState();
    };

    adjustDate('new_date', 'prev-day', 'next-day', minDate, maxDate);
});

document.addEventListener("DOMContentLoaded", () => {
    const currentDateElement = document.getElementById("current-date");
    if (currentDateElement) {
        const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
        const today = new Date();
        const dayName = days[today.getDay()];
        const formattedDate = `${dayName} ${today.getDate()}/${today.getMonth() + 1}/${today.getFullYear()}`;
        currentDateElement.textContent = formattedDate;
    }

});
