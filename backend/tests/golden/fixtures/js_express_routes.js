const express = require('express');
const router = express.Router();

router.get('/users', (req, res) => {
  res.send([]);
});

router.post('/users', (req, res) => {
  res.send({});
});

module.exports = router;
