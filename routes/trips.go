package routes

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type Trip struct {
	ID             uuid.UUID `json:"id"` // guid
	User           string    `json:"user"`
	Plates         []string  `json:"plates"`
	SubmissionDate string    `json:"submission_date"`
	From           string    `json:"from"`
	To             string    `json:"to"`
}

var trips = []Trip{
	{ID: uuid.New(), User: "John Doe", Plates: []string{"Tennessee", "Virginia"}, SubmissionDate: "2023-10-01", From: "Los Angeles", To: "San Francisco"},
	{ID: uuid.New(), User: "Jane Smith", Plates: []string{"District Of Columbia"}, SubmissionDate: "2023-10-02", From: "Chicago", To: "New York"},
	{ID: uuid.New(), User: "Alice Johnson", Plates: []string{}, SubmissionDate: "2023-10-03", From: "Miami", To: "Orlando"},
}

func RegisterTripRoutes(router *gin.Engine) {
	router.GET("/trips", func(c *gin.Context) {
		c.JSON(http.StatusOK, trips)
	})
}
