package service

import "fmt"

type User struct {
	ID   int64
	Name string
}

func (u *User) String() string {
	return fmt.Sprintf("User(%d, %s)", u.ID, u.Name)
}

func NewUser(id int64, name string) *User {
	return &User{ID: id, Name: name}
}
