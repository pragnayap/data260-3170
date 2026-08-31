"use strict";

// Validating the form using arrow function
const validateForm = () => {
    const description = document.getElementById("description").value.trim();
    const agreeTerms = document.getElementById("agreeTerms").checked;

    if (description.length <= 25) {
        alert("Incident description must be more than 25 characters.");
        return false;
    }
    if (!agreeTerms) {
        alert("You must agree to the terms and conditions before submitting.");
        return false;
    }
    return true;
}

// Closure for tracking the number of successful form submissions
const submissionCounter = (() => {
  let count = 0;
  return () => ++count;
})();

// Form submit handler
document.getElementById("incidentForm").addEventListener("submit", (e) => {
  e.preventDefault();

  if (!validateForm()) return;

  const formData = {
    routeId: document.getElementById("routeId").value,
    location: document.getElementById("location").value,
    submitterEmail: document.getElementById("submitterEmail").value,
    description: document.getElementById("description").value,
    category: document.getElementById("category").value,
    agreeTerms: document.getElementById("agreeTerms").checked,
  };

  // Converting form data to a JSON string 
  const jsonString = JSON.stringify(formData);
  console.log("Form Data (JSON string):", jsonString);

  const parsed = JSON.parse(jsonString);

  // Destructuring the primary field and email field
  const { routeId, submitterEmail } = parsed;
  console.log("Route/Line:", routeId);
  console.log("Submitter Email:", submitterEmail);

  // Spread operator- adding submissionDate to the parsed object
  const withTimestamp = { ...parsed, submissionDate: new Date().toISOString() };
  console.log("Updated Parsed Object:", withTimestamp);

  // Counting and logging how many times the form has been submitted
  const count = submissionCounter();
  console.log(`Submission count: ${count}`);

  alert("Incident reported successfully!");
  document.getElementById("incidentForm").reset();
  document.getElementById("routeId").focus();
});