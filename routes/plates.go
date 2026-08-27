package routes

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type Plate struct {
	ID                int    `json:"id" gorm:"primaryKey"`
	State             string `json:"state" gorm:"column:state"`
	Country           string `json:"country" gorm:"column:country"`
	DesignName        string `json:"design_name" gorm:"column:design_name"`
	DesignDescription string `json:"design_description" gorm:"column:design_description"`
	DesignReasoning   string `json:"design_reasoning" gorm:"column:design_reasoning"`
}

func RegisterPlateRoutes(router *gin.Engine, db *gorm.DB) {
	// get all plates
	router.GET("/plates", func(c *gin.Context) {
		var plates []Plate
		if err := db.Find(&plates).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to retrieve plates"})
			return
		}
		c.JSON(http.StatusOK, plates)
	})
	// get plate by id
	router.GET("/plates/:id", func(c *gin.Context) {
		id := c.Param("id")
		var plate Plate
		if err := db.First(&plate, id).Error; err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "Plate not found"})
			return
		}
		c.JSON(http.StatusOK, plate)
	})
}
