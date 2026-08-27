package main

import (
	"fmt"
	"go-docker-demo/routes"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func main() {
	router := gin.Default()
	host := os.Getenv("DB_HOST")
	user := os.Getenv("DB_USER")
	password := os.Getenv("DB_PASSWORD")
	dbname := os.Getenv("DB_NAME")
	port := os.Getenv("DB_PORT")
	sslmode := os.Getenv("DB_SSLMODE")

	dsn := fmt.Sprintf(
		"host=%s user=%s password=%s dbname=%s port=%s sslmode=%s",
		host, user, password, dbname, port, sslmode,
	)
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		panic("failed to connect database")
	}

	routes.RegisterJokeRoutes(router)
	routes.RegisterPlateRoutes(router, db)
	routes.RegisterTripRoutes(router)

	router.GET("/html", func(c *gin.Context) {
		c.Data(http.StatusOK, "text/html; charset=utf-8", []byte(`<h1>Hello, Gin! <span style="color:#55D7E5">ʕ◔ϖ◔ʔ</span></h1>`))
	})
	router.GET("/kiba", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message": "Hello, Kiba!",
		})
	})
	router.GET("/cicd", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message": "Hello, CI/CD!",
		})
	})
	router.POST("/ping", func(c *gin.Context) {
		var req struct {
			Message string `json:"message"`
		}
		if err := c.BindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON"})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"message": "Pong " + req.Message,
		})
	})
	router.Run(":4269")
}
