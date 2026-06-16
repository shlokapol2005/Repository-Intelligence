import React, { useState } from 'react';
import axios from 'axios';

const Checkout = () => {
  const [status, setStatus] = useState('');

  const handlePayment = async () => {
    const token = localStorage.getItem('token');
    try {
      const res = await axios.post('/api/payment', {
        token,
        amount: 4999,
        currency: 'usd',
      });
      setStatus(`Payment successful! Charge ID: ${res.data.charge_id}`);
    } catch (err) {
      setStatus('Payment failed: ' + (err.response?.data?.detail || 'Unknown error'));
    }
  };

  return (
    <div className="checkout-page">
      <h2>Checkout</h2>
      <button onClick={handlePayment}>Pay $49.99</button>
      {status && <p>{status}</p>}
    </div>
  );
};

export default Checkout;
