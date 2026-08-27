package routes

import (
	"encoding/json"
	"net/http"

	"github.com/gin-gonic/gin"
)

func RegisterJokeRoutes(router *gin.Engine) {
	router.GET("/joke", func(c *gin.Context) {
		resp, err := http.Get("https://api.cadegray.dev/joke")
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch joke"})
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch joke"})
			return
		}

		var jokes []struct {
			JokeId             int     `json:"jokeId"`
			Setup              string  `json:"setup"`
			Punchline          string  `json:"punchline"`
			FormattedPunchline string  `json:"formattedPunchline"`
			Source             *string `json:"source"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&jokes); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to decode joke"})
			return
		}

		if len(jokes) == 0 {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "No jokes found"})
			return
		}

		// Return the first joke
		c.JSON(http.StatusOK, jokes[0])
	})
}
