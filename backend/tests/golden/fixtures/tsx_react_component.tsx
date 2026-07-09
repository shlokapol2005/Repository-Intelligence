import React from 'react';

interface Props {
  label: string;
}

export const Button: React.FC<Props> = (props) => {
  return <button>{props.label}</button>;
};
