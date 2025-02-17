let documentUploaded = false;

async function uploadFile() {
    const fileInput = document.getElementById("file-upload");
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    const response = await fetch("/upload/", { method: "POST", body: formData });
    const result = await response.json();
    
    if (result.message.includes("successfully")) {
        documentUploaded = true;
        alert("Document uploaded and indexed successfully!");
    } else {
        alert("Error uploading document!");
    }
}

async function sendQuery() {
    if (!documentUploaded) {
        alert("Please upload a document first.");
        return;
    }

    const query = document.getElementById("user-query").value;
    if (!query) {
        alert("Please enter a question.");
        return;
    }

    const response = await fetch("/chat/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ "query": query })
    });

    const result = await response.json();

    if (result.response) {
        alert("AI Response: " + result.response);
    } else {
        alert("Error: " + JSON.stringify(result));
    }
}
