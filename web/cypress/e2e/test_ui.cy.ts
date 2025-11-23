describe("SIMRAI web UI – mood to queue journey", () => {
  it("brews a queue from a mood description", () => {
    // Stub the FastAPI /queue endpoint so the test is backend-independent.
    cy.intercept("POST", "http://localhost:8000/queue?theme=mario", {
      statusCode: 200,
      body: {
        mood: "rainy midnight drive",
        mood_vector: { valence: 0.4, energy: 0.3 },
        summary: "Test queue summary",
        tracks: [
          {
            name: "Test Track One",
            artists: "Test Artist",
            uri: "spotify:track:test1",
            valence: 0.4,
            energy: 0.3,
          },
        ],
      },
    }).as("brewQueue");

    cy.visit("/");

    cy.get("textarea")
      .should("be.visible")
      .type("rainy midnight drive with someone you miss");

    cy.contains("button", "Start (Warp Pipe)").click();

    cy.wait("@brewQueue");

    cy.contains("Queue").should("be.visible");
    cy.get("table tbody tr").should("have.length.at.least", 1);
    cy.contains("Test Track One").should("be.visible");
  });
});


