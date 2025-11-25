describe("SIMRAI web UI – mood to queue journey", () => {
  it("brews a queue from a mood description", () => {
    // Stub the FastAPI /queue endpoint so the test is backend-independent.
    cy.intercept("POST", "http://localhost:8000/queue", {
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

    cy.contains("button", "Generate Queue").click();

    cy.wait("@brewQueue");

    cy.contains("Queue").should("be.visible");
    cy.get("table tbody tr").should("have.length.at.least", 1);
    cy.contains("Test Track One").should("be.visible");
  });

  it("validates postMessage origin for OAuth callback", () => {
    cy.visit("/");

    // Spy on console.warn to check origin validation
    cy.window().then((win) => {
      cy.spy(win.console, "warn").as("consoleWarn");
    });

    // Simulate postMessage from untrusted origin
    cy.window().then((win) => {
      const maliciousEvent = new MessageEvent("message", {
        data: { type: "simrai-spotify-connected" },
        origin: "https://evil-site.com",  // Wrong origin
      });
      win.dispatchEvent(maliciousEvent);
    });

    // Should log warning and not connect
    cy.get("@consoleWarn").should(
      "be.calledWithMatch",
      /Rejected postMessage from untrusted origin/
    );
  });

  it("accepts postMessage from trusted origin", () => {
    // Stub the /api/me endpoint
    cy.intercept("GET", "http://localhost:8000/api/me", {
      statusCode: 200,
      body: {
        id: "test_user",
        display_name: "Test User",
        avatar_url: null,
      },
    }).as("getMe");

    cy.visit("/");

    // Simulate postMessage from trusted origin
    cy.window().then((win) => {
      const trustedEvent = new MessageEvent("message", {
        data: { type: "simrai-spotify-connected" },
        origin: "http://localhost:8000",  // Correct origin
      });
      win.dispatchEvent(trustedEvent);
    });

    // Should accept and fetch user profile
    cy.wait("@getMe");
    cy.contains("Spotify connected").should("be.visible");
  });
});


